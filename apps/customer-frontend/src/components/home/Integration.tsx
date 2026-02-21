import integrationImage1 from '@public/images/ns-img-179.png';
import integrationImage2 from '@public/images/ns-img-180.png';
import integrationImage3 from '@public/images/ns-img-181.png';
import integrationImage4 from '@public/images/ns-img-182.png';
import gradient9 from '@public/images/ns-img-501.png';
import gradient32 from '@public/images/ns-img-520.png';
import gradient33 from '@public/images/ns-img-521.png';
import gradient34 from '@public/images/ns-img-522.png';
import integrationImage2Dark from '@public/images/ns-img-dark-123.png';
import integrationImage3Dark from '@public/images/ns-img-dark-124.png';
import integrationImage4Dark from '@public/images/ns-img-dark-125.png';
import Image from 'next/image';
import Link from 'next/link';
import RevealAnimation from '../animation/RevealAnimation';
import LinkButton from '../ui/button/LinkButton';
import StackCardItem from '../ui/stack-card/StackCardItem';
import StackCardWrapper from '../ui/stack-card/StackCardWrapper';

const Integration = () => {
  return (
    <section className="pt-16 pb-16 md:pt-20 md:pb-20 lg:pt-[90px] lg:pb-[90px] xl:pt-[150px] xl:pb-[250px]">
      <div className="bg-background-2 dark:bg-background-5">
        <div className="main-container">
          <div className="flex flex-col items-start gap-x-[140px] gap-y-24 lg:flex-row">
            <div className="mx-auto w-full max-w-[520px] text-center lg:sticky lg:top-28 lg:mx-0 lg:max-w-full lg:flex-1 lg:text-left">
              <RevealAnimation delay={0.2}>
                <span className="badge badge-green mb-5">Process</span>
              </RevealAnimation>
              <RevealAnimation delay={0.3}>
                <h2 className="mb-3 max-w-[529px]">Why teams trust JobLynk for technical screening.</h2>
              </RevealAnimation>
              <RevealAnimation delay={0.4}>
                <p className="mb-7 lg:max-w-[620px]">
                  We streamline candidate evaluation with a consistent process from intake to final decision.
                </p>
              </RevealAnimation>
              <RevealAnimation delay={0.5}>
                <div>
                  <LinkButton
                    href="/process"
                    rel="noopener noreferrer"
                    className="btn btn-secondary hover:btn-primary dark:btn-transparent btn-md mx-auto w-[85%] md:w-auto">
                    Explore process
                  </LinkButton>
                </div>
              </RevealAnimation>
            </div>
            <StackCardWrapper
              topOffset="15vh"
              gap="24px"
              initDelay={100}
              className="mx-auto w-full max-w-full sm:max-w-[60%] md:max-w-[50%] lg:mx-0 lg:max-w-full lg:flex-1">
              {/* Case Item 1*/}
              <StackCardItem>
                <div className="max-w-full max-sm:min-h-[433px] lg:max-w-[483px]">
                  <div className="relative z-[10] overflow-hidden rounded-[20px] p-2.5">
                    {/* gradient border img  */}
                    <figure className="pointer-events-none absolute top-[-66%] left-[-52%] z-[-1] w-[600px] rotate-[-41deg] select-none md:top-[-99%] md:left-[-103%] md:w-[900px] xl:w-[1050px]">
                      <Image src={gradient32} alt="gradient-border" className="h-full w-full object-cover" />
                    </figure>
                    <figure className="dark:bg-background-5 space-y-6 rounded-xl bg-white p-8">
                      <figcaption className="space-y-2">
                        <h5>Define role-specific hiring criteria.</h5>
                        <p className="max-w-[250px]">
                          Build clear competencies and scorecards for each role before screening begins.
                        </p>
                      </figcaption>
                      <figure className="w-full max-w-[385px]">
                        <Image
                          src={integrationImage1}
                          alt="case icon"
                          className="w-full md:max-h-[300px] md:min-h-[300px]"
                        />
                      </figure>
                    </figure>
                  </div>
                </div>
              </StackCardItem>

              {/*Case Item 2*/}
              <StackCardItem>
                <div className="max-w-full max-sm:min-h-[433px] lg:max-w-[483px]">
                  <div className="relative z-[10] overflow-hidden rounded-[20px] p-2.5">
                    {/* gradient border img  */}
                    <figure className="pointer-events-none absolute top-[-76%] left-[-62%] z-[-1] w-[600px] rotate-[-41deg] select-none md:top-[-111%] md:left-[-103%] md:w-[900px] xl:w-[1050px]">
                      <Image src={gradient33} alt="gradient-border" className="h-full w-full object-cover" />
                    </figure>
                    <figure className="dark:bg-background-5 space-y-6 rounded-xl bg-white p-8">
                      <figcaption className="space-y-2">
                        <h5>Monitor pipeline quality and speed.</h5>
                        <p className="max-w-[250px]">Track conversion, quality signals, and time-to-hire metrics continuously.</p>
                      </figcaption>
                      <div className="w-full max-w-[400px] overflow-hidden rounded-2xl">
                        <Image
                          src={integrationImage2}
                          alt="case icon"
                          className="w-full md:max-h-[300px] md:min-h-[300px] dark:hidden"
                        />
                        <Image
                          src={integrationImage2Dark}
                          alt="case icon"
                          className="hidden w-full md:max-h-[300px] md:min-h-[300px] dark:block"
                        />
                      </div>
                    </figure>
                  </div>
                </div>
              </StackCardItem>

              {/*Case Item 3*/}
              <StackCardItem>
                <div className="max-w-full max-sm:min-h-[433px] lg:max-w-[483px]">
                  <div className="relative z-[10] overflow-hidden rounded-[20px] p-2.5">
                    {/* gradient border img  */}
                    <figure className="pointer-events-none absolute top-[-75%] left-[-65%] z-[-1] w-[600px] rotate-[-41deg] select-none md:top-[-111%] md:left-[-103%] md:w-[900px] xl:w-[1050px]">
                      <Image src={gradient34} alt="gradient-border" className="h-full w-full object-cover" />
                    </figure>
                    <figure className="dark:bg-background-5 space-y-6 rounded-xl bg-white p-8">
                      <figcaption className="space-y-2">
                        <h5>Align on hiring outcomes</h5>
                        <p className="max-w-[250px]">Set target skills, interview thresholds, and decision SLAs from day one.</p>
                      </figcaption>
                      <div className="w-full max-w-[400px] overflow-hidden rounded-2xl">
                        <Image
                          src={integrationImage3}
                          alt="case icon"
                          className="w-full md:max-h-[300px] md:min-h-[300px] dark:hidden"
                        />
                        <Image
                          src={integrationImage3Dark}
                          alt="case icon"
                          className="hidden w-full md:max-h-[300px] md:min-h-[300px] dark:block"
                        />
                      </div>
                    </figure>
                  </div>
                </div>
              </StackCardItem>

              {/*Case Item 4*/}
              <StackCardItem>
                <div className="max-w-full max-sm:min-h-[433px] lg:max-w-[483px]">
                  <div className="relative z-[10] overflow-hidden rounded-[20px] p-2.5">
                    {/* gradient border img  */}
                    <figure className="pointer-events-none absolute top-[-66%] left-[-30%] z-[-1] w-[600px] rotate-[245deg] select-none max-[376px]:left-[-40%] md:top-[-97%] md:left-[-60%] md:w-[900px] lg:left-[-48%] xl:w-[1050px]">
                      <Image src={gradient9} alt="gradient-border" className="h-full w-full object-cover" />
                    </figure>
                    <figure className="dark:bg-background-5 space-y-6 rounded-xl bg-white p-8">
                      <figcaption className="space-y-2">
                        <h5>Automate repetitive screening tasks.</h5>
                        <p className="max-w-[250px]">
                          Let automation handle scheduling, scoring, and routing so teams can focus on final hiring decisions.
                        </p>
                      </figcaption>
                      <div className="w-full max-w-[400px] overflow-hidden rounded-2xl">
                        <Link href="/process">
                          <Image
                            src={integrationImage4}
                            alt="case icon"
                            className="w-full rounded-xl md:max-h-[300px] md:min-h-[300px] dark:hidden"
                          />
                          <Image
                            src={integrationImage4Dark}
                            alt="case icon"
                            className="hidden w-full rounded-xl md:max-h-[300px] md:min-h-[300px] dark:block"
                          />
                        </Link>
                      </div>
                    </figure>
                  </div>
                </div>
              </StackCardItem>
            </StackCardWrapper>
          </div>
        </div>
      </div>
    </section>
  );
};

export default Integration;
