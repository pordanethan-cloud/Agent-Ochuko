import React from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Play, Cpu, FileText, Code, Globe, HelpCircle, Terminal, BarChart, Bug, FileEdit } from 'lucide-react'

export const Capabilities: React.FC = () => {
  const navigate = useNavigate()

  const handleTryPrompt = (promptText: string) => {
    navigate(`/?prompt=${encodeURIComponent(promptText)}`)
  }

  return (
    <div className="min-h-screen bg-white text-black flex flex-col font-['Comic_Sans_MS','Verdana','Arial',sans-serif] selection:bg-[#e8e4df] scroll-smooth" style={{ fontFamily: 'Comic Sans MS, Verdana, Arial, sans-serif' }}>
      
      {/* Authentic Top Navigation Bar */}
      <nav className="h-14 border-b border-gray-300 bg-white/90 backdrop-blur-md sticky top-0 z-50 flex items-center justify-between px-6 select-none">
        <div className="flex items-center gap-3">
          <span className="my-1 text-[13px] font-bold tracking-wider text-black uppercase">Develop AI Agents in Azure</span>
          <span className="text-gray-400">|</span>
          <span className="text-[11px] font-semibold text-gray-600 tracking-wide">Ochuko Documentation</span>
        </div>
        
        <button 
          onClick={() => navigate('/')}
          className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-gray-600 hover:text-black transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 rounded px-2 py-1"
          aria-label="Navigate back to chat"
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
              <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500 block">Sections</span>
              <ul className="space-y-2.5 text-[12px] font-medium text-gray-700">
                <li><a href="#overview" className="hover:text-black transition block focus:outline-none focus:ring-2 focus:ring-blue-600 rounded">Overview</a></li>
                <li><a href="#calculations" className="hover:text-black transition block focus:outline-none focus:ring-2 focus:ring-blue-600 rounded">Calculations & Math</a></li>
                <li><a href="#file-parsing" className="hover:text-black transition block focus:outline-none focus:ring-2 focus:ring-blue-600 rounded">File & Image Reading</a></li>
                <li><a href="#data-analysis" className="hover:text-black transition block focus:outline-none focus:ring-2 focus:ring-blue-600 rounded">Data Analysis</a></li>
                <li><a href="#code-generation" className="hover:text-black transition block focus:outline-none focus:ring-2 focus:ring-blue-600 rounded">Code Generation</a></li>
                <li><a href="#document-writing" className="hover:text-black transition block focus:outline-none focus:ring-2 focus:ring-blue-600 rounded">Document Writing</a></li>
                <li><a href="#imaging" className="hover:text-black transition block focus:outline-none focus:ring-2 focus:ring-blue-600 rounded">Image Generation</a></li>
                <li><a href="#web-search" className="hover:text-black transition block focus:outline-none focus:ring-2 focus:ring-blue-600 rounded">Live Web Search</a></li>
                <li><a href="#quick-start" className="hover:text-black transition block focus:outline-none focus:ring-2 focus:ring-blue-600 rounded">Quick Start Guide</a></li>
              </ul>
            </div>
            
            <div className="p-3 rounded-lg border border-gray-300 bg-white/60 space-y-2">
              <div className="flex items-center gap-1.5 text-[10px] text-blue-600 font-bold uppercase tracking-wider">
                <Cpu className="w-3.5 h-3.5" />
                <span>Agent Status</span>
              </div>
              <p className="text-[10px] text-gray-700 leading-relaxed">
                Ochuko is online and configured to run within secure Azure system boundaries.
              </p>
            </div>
          </nav>
        </aside>

        {/* Right Side: Main Article */}
        <article className="flex-1 max-w-3xl space-y-10 pb-20">
          
          {/* Header */}
          <div className="space-y-4 border-b border-gray-300 pb-6" id="overview">
            <h1 className="text-3xl font-semibold tracking-tight text-black">
              Build AI agents with Ochuko
            </h1>
            <p className="text-[14px] text-gray-700 leading-relaxed">
              In this guide, you will learn what Agent Ochuko can do and how to use its tools. Ochuko makes it easy to run calculations, read and analyze documents, generate designs, and retrieve live information from the web.
            </p>
            <div className="flex items-center gap-2 text-[11px] text-gray-600 font-medium bg-white border border-gray-300 px-3 py-1.5 rounded-lg w-fit">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse" />
              <span>Average reading time: <strong>3 minutes</strong></span>
            </div>
          </div>

          {/* Warning Note */}
          <blockquote className="p-4 rounded-xl border-l-4 border-blue-600 bg-blue-50 space-y-1.5">
            <p className="text-[12px] font-bold text-black uppercase tracking-wider">System Note</p>
            <p className="text-[12px] text-gray-700 leading-relaxed">
              Ochuko processes data and executes actions in a secure, isolated workspace. All uploaded files and calculation logs are kept private to your session.
            </p>
          </blockquote>

          {/* Section: Calculations & Data */}
          <section className="space-y-4" id="calculations">
            <h2 className="text-xl font-semibold text-black flex items-center gap-2 border-b border-gray-300 pb-2">
              <Terminal className="w-5 h-5 text-blue-600" />
              <span>Calculations & Data Processing</span>
            </h2>
            <p className="text-xs text-gray-700 leading-relaxed">
              Ochuko can write and run custom scripts to solve math problems, perform complex logic, and create visual data charts. Use this whenever you need precision calculations.
            </p>
            <div className="p-4 rounded-lg bg-white border border-gray-300 space-y-3">
              <div className="flex justify-between items-center text-[10px] text-gray-600 uppercase tracking-wider font-mono">
                <span>Example Inquiry</span>
                <span>Try In Chat</span>
              </div>
              <div className="flex justify-between items-center gap-4 bg-[#1a1a1a] p-3 rounded border border-gray-600">
                <code className="text-xs text-white font-mono">"Create a Python script that simulates a 100-step random walk, visualizes the path with matplotlib, and calculates statistics like average distance from origin"</code>
                <button 
                  onClick={() => handleTryPrompt("Create a Python script that simulates a 100-step random walk, visualizes the path with matplotlib, and calculates statistics like average distance from origin")}
                  className="p-1 rounded bg-[#ffffff] text-black hover:bg-white/80 active:scale-95 transition focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
                  aria-label="Try this prompt in chat"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                </button>
              </div>
            </div>
          </section>

          {/* Section: File & Image Ingestion */}
          <section className="space-y-4" id="file-parsing">
            <h2 className="text-xl font-semibold text-black flex items-center gap-2 border-b border-gray-300 pb-2">
              <FileText className="w-5 h-5 text-blue-600" />
              <span>File & Image Reading</span>
            </h2>
            <p className="text-xs text-gray-700 leading-relaxed">
              Upload spreadsheets, PDF reports, or Word documents. Ochuko automatically reads their contents, extracts key tables, and answers questions about them. You can also upload screenshots or images for OCR scanning.
            </p>
            <div className="p-4 rounded-lg bg-white border border-gray-300 space-y-3">
              <div className="flex justify-between items-center text-[10px] text-gray-600 uppercase tracking-wider font-mono">
                <span>Example Inquiry</span>
                <span>Try In Chat</span>
              </div>
              <div className="flex justify-between items-center gap-4 bg-[#1a1a1a] p-3 rounded border border-gray-600">
                <code className="text-xs text-white font-mono">"Analyze the uploaded financial report PDF, extract all revenue and expense figures, and present them in a structured markdown table with year-over-year growth calculations"</code>
                <button 
                  onClick={() => handleTryPrompt("Analyze the uploaded financial report PDF, extract all revenue and expense figures, and present them in a structured markdown table with year-over-year growth calculations")}
                  className="p-1 rounded bg-[#ffffff] text-black hover:bg-white/80 active:scale-95 transition focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
                  aria-label="Try this prompt in chat"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                </button>
              </div>
            </div>
          </section>

          {/* Section: Data Analysis */}
          <section className="space-y-4" id="data-analysis">
            <h2 className="text-xl font-semibold text-black flex items-center gap-2 border-b border-gray-300 pb-2">
              <BarChart className="w-5 h-5 text-blue-600" />
              <span>Data Analysis & Visualization</span>
            </h2>
            <p className="text-xs text-gray-700 leading-relaxed">
              Upload datasets and let Ochuko analyze patterns, create visualizations, and generate insights. From CSV files to complex data structures, get comprehensive analysis with charts and summaries.
            </p>
            <div className="p-4 rounded-lg bg-white border border-gray-300 space-y-3">
              <div className="flex justify-between items-center text-[10px] text-gray-600 uppercase tracking-wider font-mono">
                <span>Example Inquiry</span>
                <span>Try In Chat</span>
              </div>
              <div className="flex justify-between items-center gap-4 bg-[#1a1a1a] p-3 rounded border border-gray-600">
                <code className="text-xs text-white font-mono">"Analyze the uploaded sales CSV data, identify trends over the past year, create visualizations for monthly revenue, and provide actionable insights for growth"</code>
                <button 
                  onClick={() => handleTryPrompt("Analyze the uploaded sales CSV data, identify trends over the past year, create visualizations for monthly revenue, and provide actionable insights for growth")}
                  className="p-1 rounded bg-[#ffffff] text-black hover:bg-white/80 active:scale-95 transition focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
                  aria-label="Try this prompt in chat"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                </button>
              </div>
            </div>
          </section>

          {/* Section: Code Generation */}
          <section className="space-y-4" id="code-generation">
            <h2 className="text-xl font-semibold text-black flex items-center gap-2 border-b border-gray-300 pb-2">
              <Bug className="w-5 h-5 text-blue-600" />
              <span>Code Generation & Debugging</span>
            </h2>
            <p className="text-xs text-gray-700 leading-relaxed">
              Generate production-ready code in multiple programming languages, debug existing code, explain complex algorithms, and refactor for better performance and readability.
            </p>
            <div className="p-4 rounded-lg bg-white border border-gray-300 space-y-3">
              <div className="flex justify-between items-center text-[10px] text-gray-600 uppercase tracking-wider font-mono">
                <span>Example Inquiry</span>
                <span>Try In Chat</span>
              </div>
              <div className="flex justify-between items-center gap-4 bg-[#1a1a1a] p-3 rounded border border-gray-600">
                <code className="text-xs text-white font-mono">"Write a TypeScript React component for a responsive data table with sorting, filtering, and pagination, including proper TypeScript types and error handling"</code>
                <button 
                  onClick={() => handleTryPrompt("Write a TypeScript React component for a responsive data table with sorting, filtering, and pagination, including proper TypeScript types and error handling")}
                  className="p-1 rounded bg-[#ffffff] text-black hover:bg-white/80 active:scale-95 transition focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
                  aria-label="Try this prompt in chat"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                </button>
              </div>
            </div>
          </section>

          {/* Section: Document Writing */}
          <section className="space-y-4" id="document-writing">
            <h2 className="text-xl font-semibold text-black flex items-center gap-2 border-b border-gray-300 pb-2">
              <FileEdit className="w-5 h-5 text-blue-600" />
              <span>Document Writing & Formatting</span>
            </h2>
            <p className="text-xs text-gray-700 leading-relaxed">
              Create professional documents, reports, summaries, and formatted content. From technical documentation to business reports, get well-structured output in various formats.
            </p>
            <div className="p-4 rounded-lg bg-white border border-gray-300 space-y-3">
              <div className="flex justify-between items-center text-[10px] text-gray-600 uppercase tracking-wider font-mono">
                <span>Example Inquiry</span>
                <span>Try In Chat</span>
              </div>
              <div className="flex justify-between items-center gap-4 bg-[#1a1a1a] p-3 rounded border border-gray-600">
                <code className="text-xs text-white font-mono">"Write a comprehensive project proposal document including executive summary, objectives, methodology, timeline, and budget breakdown in a professional format"</code>
                <button 
                  onClick={() => handleTryPrompt("Write a comprehensive project proposal document including executive summary, objectives, methodology, timeline, and budget breakdown in a professional format")}
                  className="p-1 rounded bg-[#ffffff] text-black hover:bg-white/80 active:scale-95 transition focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
                  aria-label="Try this prompt in chat"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                </button>
              </div>
            </div>
          </section>

          {/* Section: Image Generation */}
          <section className="space-y-4" id="imaging">
            <h2 className="text-xl font-semibold text-black flex items-center gap-2 border-b border-gray-300 pb-2">
              <Code className="w-5 h-5 text-blue-600" />
              <span>Image & Design Generation</span>
            </h2>
            <p className="text-xs text-gray-700 leading-relaxed">
              Ochuko can create high-resolution designs, user interface layouts, icons, and illustrations. Tell Ochuko what style and contents you want, and it will draw it for you.
            </p>
            <div className="p-4 rounded-lg bg-white border border-gray-300 space-y-3">
              <div className="flex justify-between items-center text-[10px] text-gray-600 uppercase tracking-wider font-mono">
                <span>Example Inquiry</span>
                <span>Try In Chat</span>
              </div>
              <div className="flex justify-between items-center gap-4 bg-[#1a1a1a] p-3 rounded border border-gray-600">
                <code className="text-xs text-white font-mono">"Design a modern dark-mode dashboard UI for a task management app with a sidebar navigation, Kanban board layout, progress indicators, and clean typography using a professional color scheme"</code>
                <button 
                  onClick={() => handleTryPrompt("Design a modern dark-mode dashboard UI for a task management app with a sidebar navigation, Kanban board layout, progress indicators, and clean typography using a professional color scheme")}
                  className="p-1 rounded bg-[#ffffff] text-black hover:bg-white/80 active:scale-95 transition focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
                  aria-label="Try this prompt in chat"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                </button>
              </div>
            </div>
          </section>

          {/* Section: Live Web Search */}
          <section className="space-y-4" id="web-search">
            <h2 className="text-xl font-semibold text-black flex items-center gap-2 border-b border-gray-300 pb-2">
              <Globe className="w-5 h-5 text-blue-600" />
              <span>Live Web Search</span>
            </h2>
            <p className="text-xs text-gray-700 leading-relaxed">
              When answering questions, Ochuko can lookup real-time resources online, such as academic publications, arXiv preprints, clinical trials, and public databases.
            </p>
            <div className="p-4 rounded-lg bg-white border border-gray-300 space-y-3">
              <div className="flex justify-between items-center text-[10px] text-gray-600 uppercase tracking-wider font-mono">
                <span>Example Inquiry</span>
                <span>Try In Chat</span>
              </div>
              <div className="flex justify-between items-center gap-4 bg-[#1a1a1a] p-3 rounded border border-gray-600">
                <code className="text-xs text-white font-mono">"Search arXiv and academic sources for recent papers on large language model efficiency techniques, focusing on quantization, distillation, and inference optimization methods from the last 6 months"</code>
                <button 
                  onClick={() => handleTryPrompt("Search arXiv and academic sources for recent papers on large language model efficiency techniques, focusing on quantization, distillation, and inference optimization methods from the last 6 months")}
                  className="p-1 rounded bg-[#ffffff] text-black hover:bg-white/80 active:scale-95 transition focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2"
                  aria-label="Try this prompt in chat"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                </button>
              </div>
            </div>
          </section>

          {/* Section: Quick Start Guide */}
          <section className="space-y-4" id="quick-start">
            <h2 className="text-xl font-semibold text-black flex items-center gap-2 border-b border-gray-300 pb-2">
              <HelpCircle className="w-5 h-5 text-blue-600" />
              <span>Quick Start Guide</span>
            </h2>
            <p className="text-xs text-gray-700 leading-relaxed">
              To interact with your agent:
            </p>
            <ol className="list-decimal list-inside text-xs text-gray-700 space-y-2 pl-2">
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
