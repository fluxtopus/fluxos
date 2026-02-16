import { RocketLaunchIcon } from '@heroicons/react/24/outline'

export default function Hero() {
  return (
    <section className="relative min-h-screen flex items-center justify-center px-4 py-20 overflow-hidden">
      {/* Background grid effect */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,oklch(0.26_0.01_260)_1px,transparent_1px),linear-gradient(to_bottom,oklch(0.26_0.01_260)_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_80%_50%_at_50%_0%,#000_70%,transparent_110%)] opacity-20"></div>

      <div className="relative max-w-6xl mx-auto text-center">
        {/* Logo/Icon */}
        <div className="inline-flex items-center justify-center w-20 h-20 mb-8 rounded-full bg-primary/10 pulse-glow">
          <RocketLaunchIcon className="w-10 h-10 text-primary" />
        </div>

        {/* Main headline */}
        <h1 className="text-5xl md:text-7xl font-bold mb-6 slide-up">
          Describe It.
          <br />
          <span className="text-primary">Your AI Agents Handle the Rest.</span>
        </h1>

        {/* Subheadline */}
        <p className="text-xl md:text-2xl text-muted-foreground mb-12 max-w-3xl mx-auto fade-in" style={{ animationDelay: '0.2s' }}>
          Tell fluxos what your business needs — customer follow-ups, weekly reports, team notifications — and AI agents build, run, and maintain the workflow for you.
        </p>

        {/* CTA Button */}
        <div className="fade-in" style={{ animationDelay: '0.4s' }}>
          <a
            href="#pricing"
            className="inline-flex items-center gap-2 px-8 py-4 text-lg font-semibold bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-all hover:scale-105 shadow-lg hover:shadow-primary/50"
          >
            Get Started
            <RocketLaunchIcon className="w-5 h-5" />
          </a>
        </div>

        {/* Trust indicators */}
        <div className="mt-16 flex flex-wrap justify-center gap-4 text-sm text-muted-foreground font-mono fade-in" style={{ animationDelay: '0.6s' }}>
          <span className="px-3 py-1 border border-border rounded">[ No Coding Required ]</span>
          <span className="px-3 py-1 border border-border rounded">[ Your Data Stays Private ]</span>
          <span className="px-3 py-1 border border-border rounded">[ Works 24/7 ]</span>
        </div>
      </div>
    </section>
  )
}
