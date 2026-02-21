import { ICaseStudy } from '@/interface';
import getMarkDownData from '@/utils/getMarkDownData';
import Image from 'next/image';
import RevealAnimation from '../animation/RevealAnimation';
import LinkButton from '../ui/button/LinkButton';
const featuredProjects: ICaseStudy[] = getMarkDownData<ICaseStudy & { [key: string]: unknown }>(
  'src/data/case-study',
).slice(0, 4);

const Projects = () => {
  return (
    <section className="bg-white pt-16 pb-16 md:pt-20 md:pb-20 lg:pt-[90px] lg:pb-[90px] xl:pt-[160px] xl:pb-[160px] dark:bg-black">
      <div className="main-container">
        <div className="mb-10 space-y-5 text-center md:mb-[70px]">
          <RevealAnimation delay={0.2}>
            <span className="badge badge-green">Projects</span>
          </RevealAnimation>
          <div className="space-y-3">
            <RevealAnimation delay={0.3}>
              <h2>Proven screening projects in action.</h2>
            </RevealAnimation>
            <RevealAnimation delay={0.4}>
              <p className="mx-auto max-w-[680px]">
                Discover how JobLynk helps teams improve technical hiring outcomes with structured screening and
                candidate intelligence. Explore real implementations across different hiring scenarios.
              </p>
            </RevealAnimation>
          </div>
        </div>
        <div className="mb-14">
          <div className="grid grid-cols-12 gap-y-14 lg:gap-x-14">
            <RevealAnimation delay={0.5}>
              <div className="col-span-12">
                <figure className="space-y-6">
                  <div className="group relative h-[300px] w-full cursor-pointer overflow-hidden rounded-[20px] lg:h-[576px]">
                    <Image
                      src={featuredProjects[0].thumbnail}
                      className="h-full w-full rounded-[20px] object-cover transition-transform duration-500 group-hover:scale-110"
                      alt="portfolio"
                      fill
                      priority
                    />
                    <div className="absolute inset-0 bg-black/0 transition-all duration-500 ease-in-out group-hover:bg-black/40" />
                    <LinkButton
                      href={`/case-study/${featuredProjects[0].slug}`}
                      className="btn btn-md hover:btn-primary dark:btn-accent btn-secondary absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-[calc(50%-8px)] scale-95 transform-gpu opacity-0 transition-all duration-500 ease-out group-hover:-translate-y-1/2 group-hover:scale-110 group-hover:opacity-100">
                      View Case Study
                    </LinkButton>
                  </div>
                  <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between md:gap-4">
                    <h3 className="text-heading-6 sm:text-heading-5">{featuredProjects[0].title}</h3>
                    <p className="line-clamp-2 max-w-[257px] text-left md:text-right">
                      {featuredProjects[0].description}
                    </p>
                  </div>
                </figure>
              </div>
            </RevealAnimation>
            <RevealAnimation delay={0.6}>
              <div className="col-span-12 lg:col-span-6">
                <figure className="space-y-6">
                  <div className="group relative h-[300px] w-full cursor-pointer overflow-hidden rounded-[20px] lg:h-[576px]">
                    <Image
                      src={featuredProjects[1].thumbnail}
                      fill
                      priority
                      className="h-full w-full rounded-[20px] object-cover transition-transform duration-500 group-hover:scale-110"
                      alt="portfolio"
                    />
                    <div className="absolute inset-0 bg-black/0 transition-all duration-500 ease-in-out group-hover:bg-black/40" />
                    <LinkButton
                      href={`/case-study/${featuredProjects[1].slug}`}
                      className="btn btn-md hover:btn-primary dark:btn-accent btn-secondary absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-[calc(50%-8px)] scale-95 transform-gpu opacity-0 transition-all duration-500 ease-out group-hover:-translate-y-1/2 group-hover:scale-110 group-hover:opacity-100">
                      View Case Study
                    </LinkButton>
                  </div>
                  <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between md:gap-4">
                    <h3 className="text-heading-6 sm:text-heading-5">{featuredProjects[1].title}</h3>
                    <p className="line-clamp-2 max-w-[257px] text-left md:text-right">
                      {featuredProjects[1].description}
                    </p>
                  </div>
                </figure>
              </div>
            </RevealAnimation>
            <RevealAnimation delay={0.7}>
              <div className="col-span-12 lg:col-span-6">
                <figure className="space-y-6">
                  <div className="group relative h-[300px] w-full cursor-pointer overflow-hidden rounded-[20px] lg:h-[576px]">
                    <Image
                      src={featuredProjects[2].thumbnail}
                      fill
                      priority
                      alt="portfolio"
                      className="h-full w-full rounded-[20px] object-cover transition-transform duration-500 group-hover:scale-110"
                    />
                    <div className="absolute inset-0 bg-black/0 transition-all duration-500 ease-in-out group-hover:bg-black/40" />
                    <LinkButton
                      href={`/case-study/${featuredProjects[2].slug}`}
                      className="btn btn-md hover:btn-primary dark:btn-accent btn-secondary absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-[calc(50%-8px)] scale-95 transform-gpu opacity-0 transition-all duration-500 ease-out group-hover:-translate-y-1/2 group-hover:scale-110 group-hover:opacity-100">
                      View Case Study
                    </LinkButton>
                  </div>
                  <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between md:gap-4">
                    <h3 className="text-heading-6 sm:text-heading-5">{featuredProjects[2].title}</h3>
                    <p className="line-clamp-2 max-w-[257px] text-left md:text-right">
                      {featuredProjects[2].description}
                    </p>
                  </div>
                </figure>
              </div>
            </RevealAnimation>
            <RevealAnimation delay={0.8}>
              <div className="col-span-12">
                <figure className="space-y-6">
                  <div className="group relative h-[300px] w-full cursor-pointer overflow-hidden rounded-[20px] lg:h-[576px]">
                    <Image
                      src={featuredProjects[3].thumbnail}
                      fill
                      priority
                      className="h-full w-full rounded-[20px] object-cover transition-transform duration-500 group-hover:scale-110"
                      alt="portfolio"
                    />
                    <div className="absolute inset-0 bg-black/0 transition-all duration-500 ease-in-out group-hover:bg-black/40" />
                    <LinkButton
                      href={`/case-study/${featuredProjects[3].slug}`}
                      className="btn btn-md hover:btn-primary dark:btn-accent btn-secondary absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-[calc(50%-8px)] scale-95 transform-gpu opacity-0 transition-all duration-500 ease-out group-hover:-translate-y-1/2 group-hover:scale-110 group-hover:opacity-100">
                      View Case Study
                    </LinkButton>
                  </div>
                  <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between md:gap-4">
                    <h3 className="text-heading-6 sm:text-heading-5">{featuredProjects[3].title}</h3>
                    <p className="line-clamp-2 max-w-[257px] text-left md:text-right">
                      {featuredProjects[3].description}
                    </p>
                  </div>
                </figure>
              </div>
            </RevealAnimation>
          </div>
        </div>
        <RevealAnimation delay={0.9}>
          <div className="text-center">
            <LinkButton
              href="/case-study"
              className="btn btn-secondary btn-md hover:btn-primary dark:btn-transparent mx-auto">
              View portfolio
            </LinkButton>
          </div>
        </RevealAnimation>
      </div>
    </section>
  );
};

export default Projects;
