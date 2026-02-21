'use client';
import reviews from '@/data/json/testimonials/testimonials.json';
import Image from 'next/image';
import 'swiper/css';
import { Autoplay } from 'swiper/modules';
import { Swiper, SwiperSlide } from 'swiper/react';
import RevealAnimation from '../animation/RevealAnimation';
import GradientOverlay from '../shared/reviews/GradientOverlay';
import LinkButton from '../ui/button/LinkButton';

const Testimonial = () => {
  return (
    <section className="relative bg-white bg-[url('/images/ns-img-169.png')] bg-cover bg-top bg-no-repeat pt-[100px] pb-[100px] dark:bg-black">
      <div className="main-container">
        <div className="mb-10 flex flex-col items-center text-center md:mb-[70px]">
          <RevealAnimation delay={0.2}>
            <h2 className="mx-auto mb-4 max-w-[750px]">What hiring teams are saying.</h2>
          </RevealAnimation>
          <RevealAnimation delay={0.3}>
            <p className="mx-auto max-w-[872px]">
              Trusted by teams that need faster, fairer, and more consistent technical hiring. Hear how JobLynk helps
              organizations reduce screening bottlenecks and make better hiring decisions.
            </p>
          </RevealAnimation>
        </div>
        <RevealAnimation delay={0.4}>
          <div className="relative">
            <Swiper
              className="swiper reviews-swiper"
              spaceBetween={30}
              slidesPerView={3}
              centeredSlides={true}
              loop={true}
              speed={1500}
              autoplay={{
                delay: 3000,
                disableOnInteraction: false,
              }}
              modules={[Autoplay]}
              navigation={false}
              pagination={false}
              scrollbar={false}>
              <div className="swiper-wrapper">
                {reviews.map((review) => (
                  <SwiperSlide key={review.id} className="swiper-slide">
                    <div className="bg-background-2 dark:bg-background-5 relative z-0 mx-1 flex flex-col gap-y-8 overflow-hidden rounded-[20px] p-8 sm:mx-0">
                      <GradientOverlay />
                      <figure className="dark:ring-background-5 relative inline-block size-14 overflow-hidden rounded-full bg-linear-[156deg,_#FFF_32.92%,_#83E7EE_91%] ring-4 ring-white">
                        <Image
                          src={review.avatar}
                          height={100}
                          width={100}
                          quality={100}
                          alt="avatar"
                          className="max-w-full"
                        />
                      </figure>
                      <p className="text-secondary/60 dark:text-accent/60 review-text line-clamp-2">{review.quote}</p>
                      <div>
                        <p className="text-secondary dark:text-accent review-name text-lg leading-[1.5] font-medium">
                          {review.name}
                        </p>
                        <p className="text-secondary/60 dark:text-accent/60 text-tagline-2 review-title">
                          {review.position}
                        </p>
                      </div>
                    </div>
                  </SwiperSlide>
                ))}
              </div>
            </Swiper>
          </div>
        </RevealAnimation>
        <RevealAnimation delay={0.5}>
          <div className="mt-10 text-center">
            <LinkButton
              href="/testimonial"
              className="btn btn-secondary btn-md dark:btn-transparent dark:border-primary-50 hover:btn-primary mx-auto inline-block w-[85%] md:w-auto">
              Read more testimonials
            </LinkButton>
          </div>
        </RevealAnimation>
      </div>
    </section>
  );
};

export default Testimonial;
