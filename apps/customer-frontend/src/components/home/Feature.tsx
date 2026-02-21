import feature1 from '@public/images/ns-img-175.png';
import feature2 from '@public/images/ns-img-176.png';
import feature3 from '@public/images/ns-img-177.png';
import feature4 from '@public/images/ns-img-178.png';
import feature1Dark from '@public/images/ns-img-dark-119.png';
import feature2Dark from '@public/images/ns-img-dark-120.png';
import feature3Dark from '@public/images/ns-img-dark-121.png';
import feature4Dark from '@public/images/ns-img-dark-122.png';
import Image from 'next/image';
import RevealAnimation from '../animation/RevealAnimation';

const Feature = () => {
  return (
    <section className="bg-white pt-16 pb-16 md:pt-20 md:pb-20 lg:pt-[90px] lg:pb-[90px] xl:pt-[100px] xl:pb-[100px] dark:bg-black">
      <div className="main-container">
        <div className="mx-auto mb-10 max-w-[750px] space-y-5 text-center md:mb-[70px]">
          <RevealAnimation delay={0.2}>
            <span className="badge badge-green">Features</span>
          </RevealAnimation>
          <div>
            <RevealAnimation delay={0.3}>
              <h2 className="mb-3">Screening workflows built for hiring teams.</h2>
            </RevealAnimation>
            <RevealAnimation delay={0.4}>
              <p className="text-secondary/60 dark:text-accent/60 mx-auto max-w-[600px]">
                Practical tools to evaluate candidates consistently, reduce manual review effort, and move qualified
                talent through your pipeline faster.
              </p>
            </RevealAnimation>
          </div>
        </div>
        {/* feature Items */}
        <div className="mb-10 grid grid-cols-12 space-y-8 md:gap-8 md:space-y-0 xl:mb-18">
          <RevealAnimation delay={0.5}>
            <div className="bg-background-3 dark:bg-background-7 col-span-12 space-y-6 rounded-[20px] p-8 md:col-span-6 lg:col-span-8">
              <div className="space-y-2">
                <h5 className="max-sm:text-heading-6">Live candidate funnel and score analytics.</h5>
                <p className="max-w-[450px]">
                  Track pass rates, skill trends, and stage conversion in real time so hiring teams can quickly adapt
                  screening strategy and improve outcomes.
                </p>
              </div>
              <figure className="w-full">
                <Image
                  src={feature1}
                  alt="feature image"
                  className="hidden w-full rounded-2xl object-cover dark:block"
                />
                <Image
                  src={feature1Dark}
                  alt="feature image"
                  className="block w-full rounded-2xl object-cover dark:hidden"
                />
              </figure>
            </div>
          </RevealAnimation>
          <RevealAnimation delay={0.6}>
            <div className="bg-background-3 dark:bg-background-7 col-span-12 space-y-6 rounded-[20px] p-8 md:col-span-6 lg:col-span-4">
              <div className="space-y-2">
                <h5 className="max-sm:text-heading-6">Seamless ATS and workflow integrations.</h5>
                <p className="max-w-[220px]">Connect existing hiring tools without disrupting current processes.</p>
              </div>
              <figure className="w-full">
                <Image
                  src={feature2}
                  alt="feature image"
                  className="block w-full rounded-2xl object-cover dark:hidden"
                />
                <Image
                  src={feature2Dark}
                  alt="feature image"
                  className="hidden w-full rounded-2xl object-cover dark:block"
                />
              </figure>
            </div>
          </RevealAnimation>
          <RevealAnimation delay={0.7}>
            <div className="bg-background-3 dark:bg-background-7 col-span-12 space-y-6 rounded-[20px] p-8 md:col-span-6 lg:col-span-4">
              <div className="space-y-2">
                <h5 className="max-sm:text-heading-6">Clear role-level screening dashboards.</h5>
                <p className="">Give recruiters and hiring managers a shared view of candidate progress and quality.</p>
              </div>
              <figure className="w-full">
                <Image
                  src={feature3}
                  alt="feature image"
                  className="block w-full rounded-2xl object-cover dark:hidden"
                />
                <Image
                  src={feature3Dark}
                  alt="feature image"
                  className="hidden w-full rounded-2xl object-cover dark:block"
                />
              </figure>
            </div>
          </RevealAnimation>
          <RevealAnimation delay={0.8}>
            <div className="bg-background-3 dark:bg-background-7 col-span-12 space-y-6 rounded-[20px] p-8 md:col-span-6 lg:col-span-8">
              <div className="max-w-[285px] space-y-2">
                <h5 className="max-sm:text-heading-6">Secure, scalable hiring infrastructure.</h5>
                <p className="max-w-[311px]">
                  Run screening operations confidently on a reliable platform built for security, scale, and long-term growth.
                </p>
              </div>
              <figure className="w-full">
                <Image
                  src={feature4}
                  alt="feature image"
                  className="block h-full w-full rounded-2xl object-cover dark:hidden"
                />
                <Image
                  src={feature4Dark}
                  alt="feature image"
                  className="hidden h-full w-full rounded-2xl object-cover dark:block"
                />
              </figure>
            </div>
          </RevealAnimation>
        </div>
      </div>
    </section>
  );
};

export default Feature;
