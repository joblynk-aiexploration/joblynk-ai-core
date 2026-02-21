import crypto from 'crypto';
import nodemailer from 'nodemailer';
import Stripe from 'stripe';
import { Pool } from 'pg';

export const runtime = 'nodejs';

const stripeSecret = process.env.STRIPE_SECRET_KEY || '';
const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET || '';
const dbUrl = process.env.DATABASE_URL || '';

const SMTP_HOST = process.env.SMTP_HOST || '';
const SMTP_PORT = Number(process.env.SMTP_PORT || 587);
const SMTP_USER = process.env.SMTP_USER || '';
const SMTP_PASS = process.env.SMTP_PASS || '';
const SMTP_FROM = process.env.SMTP_FROM || SMTP_USER || 'no-reply@joblynk.ai';
const SMTP_USE_TLS = ['1', 'true', 'yes'].includes((process.env.SMTP_USE_TLS || 'true').toLowerCase());
const APP_BASE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://devscreening.joblynk.ai';

const pool = dbUrl ? new Pool({ connectionString: dbUrl }) : null;

async function ensureTables() {
  if (!pool) return;
  await pool.query(`
    CREATE TABLE IF NOT EXISTS public.stripe_subscriptions (
      id BIGSERIAL PRIMARY KEY,
      stripe_customer_id TEXT,
      stripe_subscription_id TEXT UNIQUE,
      stripe_session_id TEXT,
      stripe_price_id TEXT,
      plan TEXT,
      status TEXT,
      amount_total BIGINT,
      currency TEXT,
      customer_email TEXT,
      event_id TEXT,
      raw_event JSONB,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW()
    );
  `);

  await pool.query(`
    CREATE TABLE IF NOT EXISTS public.screening_users (
      id BIGSERIAL PRIMARY KEY,
      email TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW()
    );
  `);
}

async function upsertSubscription(eventId: string, payload: {
  customerId?: string | null;
  subscriptionId?: string | null;
  sessionId?: string | null;
  priceId?: string | null;
  plan?: string | null;
  status?: string | null;
  amountTotal?: number | null;
  currency?: string | null;
  email?: string | null;
  rawEvent: unknown;
}) {
  if (!pool || !payload.subscriptionId) return;
  await ensureTables();
  await pool.query(
    `
    INSERT INTO public.stripe_subscriptions (
      stripe_customer_id, stripe_subscription_id, stripe_session_id,
      stripe_price_id, plan, status, amount_total, currency,
      customer_email, event_id, raw_event, updated_at
    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,NOW())
    ON CONFLICT (stripe_subscription_id) DO UPDATE SET
      stripe_customer_id = EXCLUDED.stripe_customer_id,
      stripe_session_id = EXCLUDED.stripe_session_id,
      stripe_price_id = EXCLUDED.stripe_price_id,
      plan = EXCLUDED.plan,
      status = EXCLUDED.status,
      amount_total = EXCLUDED.amount_total,
      currency = EXCLUDED.currency,
      customer_email = EXCLUDED.customer_email,
      event_id = EXCLUDED.event_id,
      raw_event = EXCLUDED.raw_event,
      updated_at = NOW();
    `,
    [
      payload.customerId || null,
      payload.subscriptionId,
      payload.sessionId || null,
      payload.priceId || null,
      payload.plan || null,
      payload.status || null,
      payload.amountTotal ?? null,
      payload.currency || null,
      payload.email || null,
      eventId,
      payload.rawEvent,
    ],
  );
}

async function ensureUserAccount(email: string): Promise<{ created: boolean; password: string }> {
  const normalized = (email || '').trim().toLowerCase();
  if (!pool || !normalized) return { created: false, password: '' };
  await ensureTables();

  const existing = await pool.query('select password from public.screening_users where email=$1 limit 1', [normalized]);
  if (existing.rowCount && existing.rows[0]?.password) {
    return { created: false, password: String(existing.rows[0].password) };
  }

  const tempPassword = `JL-${crypto.randomBytes(5).toString('hex')}-A9`;
  await pool.query(
    `
      insert into public.screening_users (email, password, updated_at)
      values ($1,$2,now())
      on conflict (email) do update set
        password=excluded.password,
        updated_at=now()
    `,
    [normalized, tempPassword],
  );
  return { created: true, password: tempPassword };
}

async function sendSubscriptionApprovedEmail(toEmail: string, created: boolean, password: string, plan?: string | null) {
  if (!toEmail || !SMTP_HOST || !SMTP_USER || !SMTP_PASS) return;

  const transporter = nodemailer.createTransport({
    host: SMTP_HOST,
    port: SMTP_PORT,
    secure: false,
    auth: { user: SMTP_USER, pass: SMTP_PASS },
  });

  const loginUrl = `${APP_BASE_URL.replace(/\/$/, '')}/login`;
  const subject = 'Your JobLynk subscription is active';
  const body = created
    ? `Your subscription has been approved and your account is ready.\n\nPlan: ${plan || 'Active'}\nLogin: ${loginUrl}\nEmail: ${toEmail}\nTemporary password: ${password}\n\nPlease log in and change your password from your profile page.`
    : `Your subscription has been approved and your account is ready.\n\nPlan: ${plan || 'Active'}\nLogin: ${loginUrl}\nEmail: ${toEmail}\n\nYou can sign in with your existing credentials.`;

  await transporter.sendMail({
    from: SMTP_FROM,
    to: toEmail,
    subject,
    text: body,
  });
}

export async function POST(req: Request) {
  if (!stripeSecret || !webhookSecret) {
    return new Response('Stripe webhook not configured', { status: 500 });
  }

  const stripe = new Stripe(stripeSecret);
  const sig = req.headers.get('stripe-signature');
  if (!sig) return new Response('Missing signature', { status: 400 });

  const rawBody = await req.text();

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(rawBody, sig, webhookSecret);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Invalid signature';
    return new Response(`Webhook Error: ${msg}`, { status: 400 });
  }

  try {
    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object as Stripe.Checkout.Session;
        const subscriptionId = typeof session.subscription === 'string' ? session.subscription : null;
        const priceId = session.metadata?.priceId || null;
        const plan = session.metadata?.plan || null;
        const email = session.customer_details?.email || session.customer_email || null;

        await upsertSubscription(event.id, {
          customerId: (session.customer as string) || null,
          subscriptionId,
          sessionId: session.id,
          priceId,
          plan,
          status: session.status || 'completed',
          amountTotal: session.amount_total ?? null,
          currency: session.currency || null,
          email,
          rawEvent: event,
        });

        if (email) {
          const { created, password } = await ensureUserAccount(email);
          await sendSubscriptionApprovedEmail(email, created, password, plan);
        }
        break;
      }

      case 'customer.subscription.created':
      case 'customer.subscription.updated':
      case 'customer.subscription.deleted': {
        const sub = event.data.object as Stripe.Subscription;
        const item = sub.items.data?.[0];
        await upsertSubscription(event.id, {
          customerId: (sub.customer as string) || null,
          subscriptionId: sub.id,
          sessionId: null,
          priceId: item?.price?.id || null,
          plan: item?.price?.nickname || item?.price?.lookup_key || null,
          status: sub.status,
          amountTotal: null,
          currency: item?.price?.currency || null,
          email: null,
          rawEvent: event,
        });
        break;
      }

      default:
        break;
    }

    return new Response('ok', { status: 200 });
  } catch {
    return new Response('webhook handling failed', { status: 500 });
  }
}
