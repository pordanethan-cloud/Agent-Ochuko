import React from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Play, Cpu, FileText, Code, Globe, HelpCircle, Terminal } from 'lucide-react'

export const Capabilities: React.FC = () => {
  const navigate = useNavigate()

  const handleTryPrompt = (promptText: string) => {
    navigate(`/?prompt=${encodeURIComponent(promptText)}`)
  }

  return (
    <div className="min-h-screen bg-brand-bg text-brand-text flex flex-col font-sans selection:bg-brand-accent/20">
      
      {/* Authentic Top Navigation Bar */}
      <nav className="h-14 border-b border-brand-border bg-[#0d0f11]/80 backdrop-blur-md sticky top-0 z-50 flex items-center justify-between px-6 select-none">
        <div className="flex items-center gap-3">
          <span className="my-1 text-[13px] font-bold tracking-wider text-brand-text uppercase">Develop AI Agents in Azure</span>
          <span className="text-brand-muted/30">|</span>
          <span className="text-[11px] font-semibold text-brand-muted tracking-wide">Ochuko Documentation</span>
        </div>
        
        <button 
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand-muted hover:text-brand-text transition-colors duration-150"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Chat</span>
        </button>
      </nav>

      {/* Main Content Layout */}
      <div className="flex-1 max-w-6xl w-full mx-auto px-6 py-10 flex gap-10">
        
        {/* Left Side: Table of Contents / Sidebar Navigation */}
        <aside className="w-56 hidden md:block shrink-0">
          <nav className="sticky top-24 space-y-6">
            <div className="space-y-2">
              <span className="text-[10px] font-bold uppercase tracking-widest text-brand-muted/50 block">Sections</span>
              <ul className="space-y-2.5 text-[12px] font-medium text-brand-muted">
                <li><a href="#overview" className="hover:text-brand-text transition block">Overview</a></li>
                <li><a href="#calculations" className="hover:text-brand-text transition block">Calculations & Math</a></li>
                <li><a href="#file-parsing" className="hover:text-brand-text transition block">File & Image Reading</a></li>
                <li><a href="#imaging" className="hover:text-brand-text transition block">Image Generation</a></li>
                <li><a href="#web-search" className="hover:text-brand-text transition block">Live Web Search</a></li>
                <li><a href="#quick-start" className="hover:text-brand-text transition block">Quick Start Guide</a></li>
              </ul>
            </div>
            
            <div className="p-3 rounded-lg border border-brand-border/40 bg-brand-surface/20 space-y-2">
              <div className="flex items-center gap-1.5 text-[10px] text-brand-accent font-bold uppercase tracking-wider">
                <Cpu className="w-3.5 h-3.5" />
                <span>Agent Status</span>
              </div>
              <p className="text-[10px] text-brand-muted leading-relaxed">
                Ochuko is online and configured to run within secure Azure system boundaries.
              </p>
            </div>
          </nav>
        </aside>

        {/* Right Side: Main Article */}
        <article className="flex-1 max-w-3xl space-y-10 pb-20">
          
          {/* Header */}
          <div className="space-y-4 border-b border-brand-border/30 pb-6" id="overview">
            <h1 className="text-3xl font-semibold tracking-tight text-brand-text">
              Build AI agents with Ochuko
            </h1>
            <p className="text-[14px] text-brand-muted leading-relaxed">
              In this guide, you will learn what Agent Ochuko can do and how to use its tools. Ochuko makes it easy to run calculations, read and analyze documents, generate designs, and retrieve live information from the web.
            </p>
            <div className="flex items-center gap-2 text-[11px] text-brand-muted font-medium bg-[#ffffff]/5 border border-brand-border px-3 py-1.5 rounded-lg w-fit">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-accent animate-pulse" />
              <span>Average reading time: <strong>3 minutes</strong></span>
            </div>
          </div>

          {/* Warning Note */}
          <blockquote className="p-4 rounded-xl border-l-4 border-brand-accent bg-[#ffffff]/4 space-y-1.5">
            <p className="text-[12px] font-bold text-brand-text uppercase tracking-wider">System Note</p>
            <p className="text-[12px] text-brand-muted leading-relaxed">
              Ochuko processes data and executes actions in a secure, isolated workspace. All uploaded files and calculation logs are kept private to your session.
            </p>
          </blockquote>

          {/* Section: Calculations & Data */}
          <section className="space-y-4" id="calculations">
            <h2 className="text-xl font-semibold text-brand-text flex items-center gap-2 border-b border-brand-border/20 pb-2">
              <Terminal className="w-5 h-5 text-brand-accent" />
              <span>Calculations & Data Processing</span>
            </h2>
            <p className="text-xs text-brand-muted leading-relaxed">
              Ochuko can write and run custom scripts to solve math problems, perform complex logic, and create visual data charts. Use this whenever you need precision calculations.
            </p>
            <div className="p-4 rounded-lg bg-[#ffffff]/4 border border-brand-border space-y-3">
              <div className="flex justify-between items-center text-[10px] text-brand-muted uppercase tracking-wider font-mono">
                <span>Example Inquiry</span>
                <span>Try In Chat</span>
              </div>
              <div className="flex justify-between items-center gap-4 bg-[#08090a] p-3 rounded border border-brand-border/60">
                <code className="text-xs text-brand-text font-mono">"Write a python script to simulate a random walk of 100 steps and plot it"</code>
                <button 
                  onClick={() => handleTryPrompt("Write a python script to simulate a random walk of 100 steps and plot it")}
                  className="p-1 rounded bg-[#ffffff] text-black hover:bg-white/80 active:scale-95 transition"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                </button>
              </div>
            </div>
          </section>

          {/* Section: File & Image Ingestion */}
          <section className="space-y-4" id="file-parsing">
            <h2 className="text-xl font-semibold text-brand-text flex items-center gap-2 border-b border-brand-border/20 pb-2">
              <FileText className="w-5 h-5 text-brand-accent" />
              <span>File & Image Reading</span>
            </h2>
            <p className="text-xs text-brand-muted leading-relaxed">
              Upload spreadsheets, PDF reports, or Word documents. Ochuko automatically reads their contents, extracts key tables, and answers questions about them. You can also upload screenshots or images for OCR scanning.
            </p>
            <div className="p-4 rounded-lg bg-[#ffffff]/4 border border-brand-border space-y-3">
              <div className="flex justify-between items-center text-[10px] text-brand-muted uppercase tracking-wider font-mono">
                <span>Example Inquiry</span>
                <span>Try In Chat</span>
              </div>
              <div className="flex justify-between items-center gap-4 bg-[#08090a] p-3 rounded border border-brand-border/60">
                <code className="text-xs text-brand-text font-mono">"Read this PDF and summarize the main financial data in a table"</code>
                <button 
                  onClick={() => handleTryPrompt("Read this PDF and summarize the main financial data in a table")}
                  className="p-1 rounded bg-[#ffffff] text-black hover:bg-white/80 active:scale-95 transition"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                </button>
              </div>
            </div>
          </section>

          {/* Section: Image Generation */}
          <section className="space-y-4" id="imaging">
            <h2 className="text-xl font-semibold text-brand-text flex items-center gap-2 border-b border-brand-border/20 pb-2">
              <Code className="w-5 h-5 text-brand-accent" />
              <span>Image & Design Generation</span>
            </h2>
            <p className="text-xs text-brand-muted leading-relaxed">
              Ochuko can create high-resolution designs, user interface layouts, icons, and illustrations. Tell Ochuko what style and contents you want, and it will draw it for you.
            </p>
            <div className="p-4 rounded-lg bg-[#ffffff]/4 border border-brand-border space-y-3">
              <div className="flex justify-between items-center text-[10px] text-brand-muted uppercase tracking-wider font-mono">
                <span>Example Inquiry</span>
                <span>Try In Chat</span>
              </div>
              <div className="flex justify-between items-center gap-4 bg-[#08090a] p-3 rounded border border-brand-border/60">
                <code className="text-xs text-brand-text font-mono">"Generate a modern dark-mode mockup for a task tracking app dashboard"</code>
                <button 
                  onClick={() => handleTryPrompt("Generate a modern dark-mode mockup for a task tracking app dashboard")}
                  className="p-1 rounded bg-[#ffffff] text-black hover:bg-white/80 active:scale-95 transition"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                </button>
              </div>
            </div>
          </section>

          {/* Section: Live Web Search */}
          <section className="space-y-4" id="web-search">
            <h2 className="text-xl font-semibold text-brand-text flex items-center gap-2 border-b border-brand-border/20 pb-2">
              <Globe className="w-5 h-5 text-brand-accent" />
              <span>Live Web Search</span>
            </h2>
            <p className="text-xs text-brand-muted leading-relaxed">
              When answering questions, Ochuko can lookup real-time resources online, such as academic publications, arXiv preprints, clinical trials, and public databases.
            </p>
            <div className="p-4 rounded-lg bg-[#ffffff]/4 border border-brand-border space-y-3">
              <div className="flex justify-between items-center text-[10px] text-brand-muted uppercase tracking-wider font-mono">
                <span>Example Inquiry</span>
                <span>Try In Chat</span>
              </div>
              <div className="flex justify-between items-center gap-4 bg-[#08090a] p-3 rounded border border-brand-border/60">
                <code className="text-xs text-brand-text font-mono">"Search for the latest research preprints on AI model efficiency"</code>
                <button 
                  onClick={() => handleTryPrompt("Search for the latest research preprints on AI model efficiency")}
                  className="p-1 rounded bg-[#ffffff] text-black hover:bg-white/80 active:scale-95 transition"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                </button>
              </div>
            </div>
          </section>

          {/* Section: Quick Start Guide */}
          <section className="space-y-4" id="quick-start">
            <h2 className="text-xl font-semibold text-brand-text flex items-center gap-2 border-b border-brand-border/20 pb-2">
              <HelpCircle className="w-5 h-5 text-brand-accent" />
              <span>Quick Start Guide</span>
            </h2>
            <p className="text-xs text-brand-muted leading-relaxed">
              To interact with your agent:
            </p>
            <ol className="list-decimal list-inside text-xs text-brand-muted space-y-2 pl-2">
              <li>Navigate to the main chat page using the navigation bar.</li>
              <li>Select your desired mode (<strong>Think</strong> for structured logic, <strong>Solve</strong> for actions, or <strong>Discuss</strong> for basic conversation).</li>
              <li>Type your query in the floating input bar and click <strong>Send</strong>.</li>
            </ol>
          </section>

        </article>

      </div>
    </div>
  )
}
