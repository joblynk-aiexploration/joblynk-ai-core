'use client';
import { useParallaxEffect } from '@/hooks/useParallaxEffect';
import { CheckIcon, DownArrowIcon, TransferSuccessIcon, UpArrowIcon } from '@/icons';
import avatar9 from '@public/images/ns-avatar-9.png';
import heroBottomImage from '@public/images/ns-img-171.png';
import heroLeftCursor from '@public/images/ns-img-172.svg';
import heroImage from '@public/images/ns-img-173.png';
import misc06 from '@public/images/ns-img-174.png';
import gradient12 from '@public/images/ns-img-504.png';
import badge3 from '@public/images/ns-img-66.svg';
import heroLeftCursorDark from '@public/images/ns-img-dark-116.svg';
import heroImageDark from '@public/images/ns-img-dark-117.png';
import misc06Dark from '@public/images/ns-img-dark-118.png';
import badgeDark3 from '@public/images/ns-img-dark-43.svg';
import Image from 'next/image';
import NumberAnimation from '../animation/NumberAnimation';
import RevealAnimation from '../animation/RevealAnimation';
import Progress from '../home/Progress';
import LinkButton from '../ui/button/LinkButton';

const benefits = [
  {
    id: 1,
    text: 'Screen candidates faster with AI-assisted technical evaluation.',
  },
  {
    id: 2,
    text: 'Built for hiring teams, recruiters, and engineering leaders.',
  },
  {
    id: 3,
    text: 'Move from resume to shortlist with clarity and confidence.',
  },
];

const experienceList = [
  {
    id: 1,
    text: 'Role-aligned screening workflows for modern engineering hiring.',
  },
  {
    id: 2,
    text: 'Structured assessments, scorecards, and transparent candidate feedback.',
  },
  {
    id: 3,
    text: 'Designed to reduce bias, improve consistency, and speed up decisions.',
  },
];

const Hero = () => {
  const sceneRef = useParallaxEffect();
  return (
    <section
      ref={sceneRef}
      className="relative z-0 bg-[url('/images/ns-img-169.png')] bg-top bg-no-repeat pt-[320px] pb-16 md:pt-[200px] md:pb-20 lg:pt-[200px] lg:pb-[120px] xl:pt-[260px] xl:pb-[150px]"
      id="scene">
      {/*Hero Title Content*/}
      <div className="main-container relative z-10 mb-[100px] flex flex-col items-center space-y-[124px] lg:mb-[150px] xl:mb-[220px]">
        {/*Hero shape left item*/}
        <div className="absolute -top-[160px] left-5 -z-10 w-[323px] md:-top-[80px] md:rotate-8 lg:top-[50px] lg:left-[50px] 2xl:-left-[120px]">
          <RevealAnimation delay={0.9} useSpring offset={100} duration={1.9}>
            <figure
              className="parallax-effect absolute top-0 right-0 w-[112px]"
              data-parallax-value="1.2"
              data-parallax-y="1.2"
              data-parallax-x="1.2">
              <Image src={heroLeftCursor} alt="shape" className="h-full w-full dark:hidden" />
              <Image src={heroLeftCursorDark} alt="shape" className="hidden h-full w-full dark:inline-block" />
            </figure>
          </RevealAnimation>
          <RevealAnimation delay={0.8} useSpring offset={80} duration={2.9}>
            <div className="absolute top-[60px] left-0 w-[256px] space-y-4 md:left-6 lg:top-[160px] lg:left-0 xl:top-[60px]">
              <div
                data-progress-item=""
                data-progress-value={48}
                className="w-full space-y-4 rounded-xl bg-white p-4 dark:bg-black">
                {/* heading  */}
                <div className="flex items-center justify-between">
                  <p className="text-secondary dark:text-accent leading-[150%]">Credit limit</p>
                  <p className="text-secondary dark:text-accent flex items-center text-lg leading-[150%] font-medium">
                    $
                    <NumberAnimation number={80224} speed={2000} interval={200} rooms={5} heightSpaceRatio={2.5} />
                  </p>
                </div>
                {/* progress bar  */}
                <Progress />
              </div>
              <div className="flex w-full gap-4">
                {/* transfer success  */}
                <div className="bg-secondary dark:bg-background-9 flex h-24 w-[153px] shrink-0 flex-col items-center gap-1 rounded-xl p-4">
                  <span>
                    <TransferSuccessIcon />
                  </span>
                  <span className="text-white dark:text-white"> Transfer success! </span>
                </div>
                <div className="bg-background-1 dark:bg-secondary flex items-center justify-center rounded-xl p-4">
                  <Image
                    src={avatar9}
                    alt="shape"
                    className="size-[56px] rounded-full bg-linear-[156deg,_#FFF_32.92%,_#C6F56F_91%]"
                  />
                </div>
              </div>
            </div>
          </RevealAnimation>
        </div>
        {/*Hero shape right item*/}
        <div className="absolute -top-[200px] right-5 -z-12 w-[323px] -rotate-8 md:-top-[80px] lg:top-[50px] lg:right-[50px] 2xl:-right-[120px]">
          <RevealAnimation delay={0.9} useSpring offset={100} duration={1.9}>
            <figure
              className="parallax-effect absolute top-0 left-0 hidden w-[132px] sm:block"
              data-parallax-value="1.2"
              data-parallax-y="1.2"
              data-parallax-x="-1.2">
              <Image src={badge3} alt="shape" className="h-full w-full dark:hidden" />
              <Image src={badgeDark3} alt="shape" className="hidden h-full w-full dark:inline-block" />
            </figure>
          </RevealAnimation>
          <RevealAnimation delay={0.9} useSpring offset={50} duration={3.9}>
            <div className="absolute top-[60px] hidden w-[250px] rounded-2xl bg-white p-4 sm:right-5 sm:block lg:top-[150px] lg:w-[270px] lg:p-6 xl:top-[60px] xl:right-0 2xl:w-[288px] dark:bg-black">
              <div className="text-left">
                <span className="text-tagline-2 text-secondary dark:text-accent font-normal">Total balance</span>
                <h3 className="text-heading-5 lg:text-heading-3 mt-2 mb-[30px] flex items-center leading-[1.2] font-normal">
                  $
                  <NumberAnimation number={45324} speed={2000} interval={200} rooms={5} heightSpaceRatio={2} />
                </h3>
              </div>
              <div className="flex gap-1 lg:gap-3">
                <div className="bg-secondary dark:bg-background-7 flex-1 space-y-2 rounded-xl p-4 text-left">
                  <div className="text-tagline-2 text-accent dark:text-accent flex items-center justify-start gap-2">
                    Income
                    <span className="bg-ns-green flex size-[18px] items-center justify-center rounded-full p-1">
                      <DownArrowIcon className="h-[9px] w-[8px]" />
                    </span>
                  </div>
                  <div className="text-accent dark:text-accent flex items-center text-lg leading-[1.5] font-medium">
                    $
                    <NumberAnimation number={48000} speed={2000} interval={200} rooms={5} heightSpaceRatio={2.5} />
                  </div>
                </div>
                <div className="bg-background-4 dark:bg-background-5 flex-1 space-y-2 rounded-xl p-4 text-left">
                  <div className="text-tagline-2 text-secondary dark:text-accent flex items-center justify-start gap-2">
                    Expenses
                    <span className="bg-ns-red flex size-[18px] items-center justify-center rounded-full p-1">
                      <UpArrowIcon className="h-[9px] w-[8px]" />
                    </span>
                  </div>
                  <div className="text-secondary dark:text-accent flex items-center text-lg leading-[1.5] font-medium">
                    $
                    <NumberAnimation number={2321} speed={2000} interval={200} rooms={5} heightSpaceRatio={2.5} />
                  </div>
                </div>
              </div>
            </div>
          </RevealAnimation>
        </div>
        <div className="text-left max-lg:pt-[200px] max-md:pt-[150px] md:text-center">
          <RevealAnimation delay={0.2}>
            <h1 className="mb-4">
              Hire smarter. <br className="hidden md:block" />
              Screen faster.
            </h1>
          </RevealAnimation>
          <RevealAnimation delay={0.3}>
            <p className="mx-auto mb-6 max-w-[650px]">
              &nbsp;Accelerate technical hiring with AI-assisted screening, role-based scoring, and streamlined candidate workflows from JobLynk.
            </p>
          </RevealAnimation>
          <ul className="mb-14 flex w-fit list-none flex-col gap-4 md:mx-auto md:flex-row md:flex-wrap md:items-center md:justify-center md:gap-9 lg:flex-nowrap">
            {benefits.map((item, idx) => (
              <RevealAnimation key={item.id} delay={0.4 + idx * 0.1}>
                <li className="flex items-center gap-2.5">
                  <span className="bg-secondary dark:bg-accent/20 size-[19px] rounded-full">
                    <CheckIcon className="dark:fill-accent h-[18px] w-[18px] fill-white" />
                  </span>
                  <span className="text-tagline-2 dark:text-accent/60">{item.text}</span>
                </li>
              </RevealAnimation>
            ))}
          </ul>
          <RevealAnimation delay={0.7}>
            <div className="block md:inline-block">
              <LinkButton
                href="/pricing"
                className="btn btn-primary hover:btn-white dark:btn-accent btn-xl dark:hover:btn-primary mx-auto w-[90%] md:w-auto"
                aria-label="Start building free">
                Get started
              </LinkButton>
            </div>
          </RevealAnimation>
          <RevealAnimation delay={0.8} instant duration={0.9}>
            <figure className="mx-auto mt-20 flex max-w-[408px] items-center justify-center overflow-hidden rounded-[20px] md:mt-[124px]">
              <Image src={heroImage} alt=" hero" className="inline-block h-full w-full object-cover dark:hidden" />
              <Image src={heroImageDark} alt=" hero" className="hidden h-full w-full object-cover dark:inline-block" />
            </figure>
          </RevealAnimation>
        </div>
      </div>
      {/*Hero Bottom item*/}
      <div className="main-container">
        <div className="relative z-0">
          <div className="dark:bg-background-8 absolute -z-10 h-full w-full overflow-hidden rounded-[20px] bg-white">
            <RevealAnimation delay={0.7} useSpring offset={140} direction="right">
              <div className="pointer-events-none absolute -top-[75%] -right-[75%] -z-10 size-[1060px] rotate-[10deg] select-none md:-top-[65%] md:-right-[70%] md:rotate-[60deg] lg:-top-[155%] lg:-right-[40%]">
                <Image src={gradient12} alt="gradient" />
              </div>
            </RevealAnimation>
          </div>
          <div className="flex flex-col lg:flex-row">
            <div className="py-16 max-lg:px-5 max-sm:overflow-hidden lg:flex-1/2 lg:pl-14">
              <div className="mb-9">
                <RevealAnimation delay={0.2}>
                  <h2 className="mb-3">Talent intelligence for hiring impact.</h2>
                </RevealAnimation>
                <RevealAnimation delay={0.3}>
                  <p className="max-w-[530px]">
                    At JobLynk, we combine AI screening, structured evaluation, and workflow automation to help teams
                    identify top candidates faster and hire with confidence.
                  </p>
                </RevealAnimation>
              </div>
              <ul className="mb-14 list-none space-y-2">
                {experienceList.map((item, idx) => (
                  <RevealAnimation key={item.id} delay={0.4 + idx * 0.1}>
                    <li className="flex items-center gap-3">
                      <span className="bg-secondary dark:bg-accent/20 flex size-[19px] items-center justify-center rounded-full">
                        <CheckIcon className="h-[18px] w-[18px] fill-white" />
                      </span>
                      <p className="text-secondary dark:text-accent">{item.text}</p>
                    </li>
                  </RevealAnimation>
                ))}
              </ul>
              <RevealAnimation delay={0.7}>
                <div className="text-center sm:text-left">
                  <LinkButton
                    href="/about"
                    className="btn btn-secondary btn-md hover:btn-primary dark:btn-accent mx-auto w-[85%] md:w-auto">
                    Discover more about us
                  </LinkButton>
                </div>
              </RevealAnimation>
            </div>
            <div className="lg:flex-1/2 lg:pe-[42px]">
              <RevealAnimation delay={0.5} direction="right">
                <div className="relative h-full max-lg:mx-auto max-lg:max-w-[525px]">
                  <figure className="absolute top-[100px] -left-5 w-full max-w-[152px] -rotate-[30deg] md:top-[200px] md:left-0 lg:top-10 lg:left-2">
                    <Image src={misc06} alt="shape" className="h-fill w-full dark:hidden" />
                    <Image src={misc06Dark} alt="shape" className="hidden h-full w-full dark:inline-block" />
                  </figure>
                  <figure className="max-w-[525px] max-lg:mx-auto lg:absolute lg:right-0 lg:bottom-0">
                    <Image src={heroBottomImage} alt="shape" className="h-full w-full" />
                  </figure>
                </div>
              </RevealAnimation>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default Hero;
