import { Hero } from '@/components/marketing/hero'
import { Features } from '@/components/marketing/features'
import { TechnicalSpecs } from '@/components/marketing/technical-specs'
import { DemoSection } from '@/components/marketing/demo-section'
import { IntegrationShowcase } from '@/components/marketing/integration-showcase'
import { UseCases } from '@/components/marketing/use-cases'
import { Footer } from '@/components/marketing/footer'

export default function Home() {
  return (
    <main className="min-h-screen">
      <Hero />
      <Features />
      <IntegrationShowcase />
      <TechnicalSpecs />
      <UseCases />
      <DemoSection />
      <Footer />
    </main>
  )
}
