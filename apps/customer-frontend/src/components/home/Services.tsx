import RevealAnimation from '../animation/RevealAnimation';
import LinkButton from '../ui/button/LinkButton';

const Services = () => {
  return (
    <section className="bg-[url('/images/ns-img-169.png')] bg-cover bg-top bg-no-repeat pt-16 pb-16 md:pt-20 md:pb-20 lg:pt-[90px] lg:pb-[90px] xl:pt-[100px] xl:pb-[100px]">
      <div className="main-container">
        <div className="mx-auto mb-14 max-w-[750px] space-y-5 text-center">
          <RevealAnimation delay={0.2}>
            <span className="badge badge-green">Services</span>
          </RevealAnimation>
          <div>
            <RevealAnimation delay={0.3}>
              <h2 className="mb-3">Hiring services designed for real screening outcomes.</h2>
            </RevealAnimation>
            <RevealAnimation delay={0.4}>
              <p className="mx-auto max-w-[600px]">
                From process design to implementation, our solutions modernize how teams source, screen, and select talent.
              </p>
            </RevealAnimation>
          </div>
        </div>
        {/* feature Items */}
        <div className="mx-auto mb-10 grid max-w-[1010px] grid-cols-12 space-y-8 md:gap-8 md:space-y-0 lg:mb-18">
          <RevealAnimation delay={0.5}>
            <div className="dark:bg-background-6 col-span-12 space-y-6 rounded-[20px] bg-white p-8 sm:min-h-[288px] md:col-span-6 lg:col-span-7">
              <div className="w-full">
                <span className="ns-shape-8 text-secondary dark:text-accent text-[52px]" />
              </div>
              <div className="space-y-2">
                <h5 className="max-sm:text-heading-6">Real-time screening analytics and reporting.</h5>
                <p className="max-w-[430px]">
                  Turn interview and assessment activity into actionable insight for faster, evidence-based hiring decisions.
                </p>
              </div>
            </div>
          </RevealAnimation>
          <RevealAnimation delay={0.6}>
            <div className="dark:bg-background-6 col-span-12 space-y-6 rounded-[20px] bg-white p-8 sm:min-h-[288px] md:col-span-6 lg:col-span-5">
              <div className="w-full">
                <span className="ns-shape-35 text-secondary dark:text-accent text-[52px]" />
              </div>
              <div className="space-y-2">
                <h5 className="max-sm:text-heading-6">AI-powered screening workflows.</h5>
                <p>Use AI-assisted scoring and evaluation flows to reduce manual effort and improve consistency.</p>
              </div>
            </div>
          </RevealAnimation>
          <RevealAnimation delay={0.7}>
            <div className="dark:bg-background-6 col-span-12 space-y-6 rounded-[20px] bg-white p-8 sm:min-h-[288px] md:col-span-6 lg:col-span-5">
              <div className="w-full">
                <span className="ns-shape-41 text-secondary dark:text-accent text-[52px]" />
              </div>
              <div className="space-y-2">
                <h5 className="max-sm:text-heading-6">End-to-end hiring process consulting.</h5>
                <p className="max-w-[430px]">
                  Define role-specific screening frameworks and hiring playbooks tailored to your organization.
                </p>
              </div>
            </div>
          </RevealAnimation>
          <RevealAnimation delay={0.8}>
            <div className="dark:bg-background-6 col-span-12 space-y-6 rounded-[20px] bg-white p-8 sm:min-h-[288px] md:col-span-6 lg:col-span-7">
              <div className="w-full">
                <span className="ns-shape-19 text-secondary dark:text-accent text-[52px]" />
              </div>
              <div className="space-y-2">
                <h5 className="max-sm:text-heading-6">Assessment and scoring model customization.</h5>
                <p className="max-w-[430px]">
                  Configure role-based rubrics, weighted scoring, and evaluation logic that align with your hiring standards.
                </p>
              </div>
            </div>
          </RevealAnimation>
        </div>
        <RevealAnimation delay={0.9}>
          <div className="flex items-center justify-center">
            <LinkButton
              href="/contact-us"
              className="btn btn-secondary hover:btn-primary dark:btn-transparent dark:border-primary-50 btn-md mx-auto w-[85%] md:w-auto">
              Talk to our team
            </LinkButton>
          </div>
        </RevealAnimation>
      </div>
    </section>
  );
};

export default Services;
