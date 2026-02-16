'use client'

import dynamic from 'next/dynamic'

const OceanBackground = dynamic(() => import('@/components/OceanBackground'), {
  ssr: false,
})

export default function Home() {
  return (
    <main className="min-h-screen bg-[#0b0d10] text-[#728c96] relative overflow-hidden font-mono text-sm selection:bg-[#3b6e75] selection:text-white">
      <OceanBackground />

      {/* Terminal Overlay */}
      <div className="relative z-10 min-h-screen p-6 md:p-12 flex flex-col justify-between pointer-events-none">
        
        {/* Top Bar / Header */}
        <div className="flex justify-between items-start pointer-events-auto">
          <div className="space-y-1">
            <p className="text-[#3b6e75]">STATUS: <span className="text-[#a8b8bf]">ACTIVE</span></p>
            <p className="text-[#2d4f56]">AGENTS: <span className="text-[#a8b8bf]">READY</span></p>
          </div>
          <div className="text-right space-y-1 hidden sm:block">
             <p className="text-[#2d4f56]">WORKFLOWS: <span className="text-[#a8b8bf]">RUNNING</span></p>
             <p className="text-[#3b6e75]">YOUR.DATA: <span className="text-[#a8b8bf]">PRIVATE</span></p>
          </div>
        </div>

        {/* Main Terminal Content */}
        <div className="max-w-2xl mt-10 pointer-events-auto bg-[#0b0d10]/60 backdrop-blur-sm p-6 border border-[#1b2b34] hover:border-[#3b6e75]/50 transition-colors duration-500">
          <div className="space-y-4">
            <div className="flex gap-4 border-b border-[#1b2b34] pb-4 mb-6">
               <span className="text-[#3b6e75] font-bold">FluxOS</span>
               <span className="text-[#5a6f7a]">AI Agents for Your Business</span>
               <span className="text-[#2d4f56] animate-pulse">● ONLINE</span>
            </div>

            {/* Log Entries */}
            <div className="space-y-6 font-mono">

              <div className="flex gap-4 group">
                <div className="text-[#485a62] w-16 shrink-0">00:01:22</div>
                <div className="space-y-1">
                  <p className="text-[#3b6e75] group-hover:text-[#a8b8bf] transition-colors">&gt; DESCRIBE YOUR GOAL</p>
                  <p className="text-[#5a6f7a]">
                    Tell fluxos what you need in plain English.
                    No templates. No coding. Just say what needs to happen.
                  </p>
                </div>
              </div>

              <div className="flex gap-4 group">
                <div className="text-[#485a62] w-16 shrink-0">00:01:45</div>
                <div className="space-y-1">
                  <p className="text-[#3b6e75] group-hover:text-[#a8b8bf] transition-colors">&gt; AI AGENTS BUILD THE WORKFLOW</p>
                  <p className="text-[#5a6f7a]">
                    Your agents plan the steps, connect the tools,
                    and handle the logic. You just approve and go.
                  </p>
                </div>
              </div>

              <div className="flex gap-4 group">
                <div className="text-[#485a62] w-16 shrink-0">00:02:10</div>
                <div className="space-y-1">
                   <p className="text-[#3b6e75] group-hover:text-[#a8b8bf] transition-colors">&gt; IT RUNS. IT LEARNS. IT RECOVERS.</p>
                   <p className="text-[#5a6f7a]">
                     Workflows run on autopilot. Your agents learn your preferences
                     and fix problems on their own. You stay in control.
                   </p>
                </div>
              </div>

              <div className="flex gap-4 pt-4 border-t border-[#1b2b34]">
                 <div className="text-[#485a62] w-16 shrink-0">00:02:55</div>
                 <div className="space-y-3">
                   <p className="text-[#2d4f56] animate-pulse">&gt; READY TO LET AGENTS RUN YOUR BUSINESS...</p>
                   <a
                     href="/automate-your-business"
                     className="inline-block border border-[#3b6e75] text-[#a8b8bf] py-2 px-4 text-xs uppercase tracking-wider hover:bg-[#3b6e75]/20 hover:border-[#a8b8bf]/40 transition-all"
                   >
                     See Your Automation Plan &gt;
                   </a>
                 </div>
              </div>

            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-between items-end text-[#485a62] pointer-events-auto">
          <div className="space-y-1">
             <p>INSTRUCTED.BY: <span className="text-[#5a6f7a]">JV</span></p>
             <p>SYS.ID: <span className="text-[#5a6f7a]">FLX-2026-X1</span></p>
          </div>
          
          <div className="flex gap-8">
            <a
              href="https://fluxtopus.com"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-[#3b6e75] transition-colors flex items-center gap-2 group"
            >
              <span>[SITE]</span>
              <span className="opacity-0 group-hover:opacity-100 text-[#3b6e75] transition-opacity">&lt;&lt;</span>
            </a>
            <a
              href="https://fluxtopus.com"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-[#3b6e75] transition-colors flex items-center gap-2 group"
            >
              <span>[CONTACT]</span>
              <span className="opacity-0 group-hover:opacity-100 text-[#3b6e75] transition-opacity">&lt;&lt;</span>
            </a>
          </div>
        </div>

      </div>
    </main>
  )
}
