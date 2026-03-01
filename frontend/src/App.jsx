import { useState } from "react"
import NewsSection         from "./components/NewsSection"
import RestaurantsSection  from "./components/RestaurantsSection"
import EventsSection       from "./components/EventsSection"
import DevelopmentSection  from "./components/DevelopmentSection"

const TABS = [
  { id: "news",         label: "News",         icon: "📰" },
  { id: "restaurants",  label: "Restaurants",  icon: "🍽️" },
  { id: "events",       label: "Events",       icon: "🎉" },
  { id: "development",  label: "Development",  icon: "🏗️" },
]

export default function App() {
  const [tab, setTab] = useState("news")

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-3">
          <span className="text-xl">🌆</span>
          <h1 className="text-lg font-bold text-gray-900 tracking-tight">WestervillePulse</h1>
          <span className="text-xs text-gray-400 ml-1 hidden sm:block">Westerville, OH</span>
        </div>

        {/* Tab nav */}
        <div className="max-w-5xl mx-auto px-4">
          <div className="flex gap-1">
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                  tab === t.id
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                }`}
              >
                <span>{t.icon}</span>
                <span className="hidden sm:inline">{t.label}</span>
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-5xl mx-auto px-4 py-6">
        {tab === "news"        && <NewsSection />}
        {tab === "restaurants" && <RestaurantsSection />}
        {tab === "events"      && <EventsSection />}
        {tab === "development" && <DevelopmentSection />}
      </main>
    </div>
  )
}
