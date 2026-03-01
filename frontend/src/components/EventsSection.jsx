import { useState, useEffect } from "react"
import { fetchEvents } from "../api"

function formatDate(iso) {
  if (!iso) return "TBD"
  const d = new Date(iso + "T00:00:00")
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })
}

export default function EventsSection() {
  const [events, setEvents]   = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)
  const [filter, setFilter]   = useState("All")
  const [freeOnly, setFree]   = useState(false)

  useEffect(() => {
    fetchEvents()
      .then(setEvents)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const categories = ["All", ...Array.from(new Set(events.flatMap(e => e.categories))).sort()]
  const visible = events.filter(e =>
    (filter === "All" || e.categories.includes(filter)) &&
    (!freeOnly || e.is_free)
  )

  if (loading) return <p className="text-gray-500 py-8 text-center">Loading events...</p>
  if (error)   return <p className="text-red-500 py-8 text-center">Error: {error}</p>

  return (
    <div>
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <div className="flex flex-wrap gap-2">
          {categories.map(cat => (
            <button key={cat} onClick={() => setFilter(cat)}
              className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                filter === cat ? "bg-green-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}>{cat}</button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer ml-auto">
          <input type="checkbox" checked={freeOnly} onChange={e => setFree(e.target.checked)}
            className="rounded" />
          Free events only
        </label>
      </div>

      {/* Event list */}
      <div className="space-y-3">
        {visible.map(ev => (
          <div key={ev.id} className="bg-white rounded-lg border border-gray-200 p-4 flex gap-4">
            {/* Date column */}
            <div className="text-center min-w-[64px]">
              <div className="text-xs text-gray-400 uppercase tracking-wide">
                {ev.start_date ? new Date(ev.start_date + "T00:00:00").toLocaleDateString("en-US", { month: "short" }) : ""}
              </div>
              <div className="text-2xl font-bold text-gray-800 leading-none">
                {ev.start_date ? new Date(ev.start_date + "T00:00:00").getDate() : "?"}
              </div>
              <div className="text-xs text-gray-400">
                {ev.start_date ? new Date(ev.start_date + "T00:00:00").toLocaleDateString("en-US", { weekday: "short" }) : ""}
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                {ev.is_free && (
                  <span className="text-xs bg-green-100 text-green-800 font-medium px-2 py-0.5 rounded-full">FREE</span>
                )}
                {ev.categories.map(c => (
                  <span key={c} className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{c}</span>
                ))}
              </div>

              <h3 className="font-semibold text-gray-900 leading-snug">
                {ev.event_url
                  ? <a href={ev.event_url} target="_blank" rel="noreferrer" className="hover:text-green-600 transition-colors">{ev.name}</a>
                  : ev.name}
              </h3>

              {ev.location && <p className="text-sm text-gray-500 mt-0.5">{ev.location}</p>}
              {ev.description && (
                <p className="text-sm text-gray-400 mt-1 line-clamp-2">{ev.description}</p>
              )}

              <div className="flex items-center gap-3 mt-2">
                {ev.cost && !ev.is_free && (
                  <span className="text-sm text-gray-600">{ev.cost}</span>
                )}
                {ev.tickets_url && (
                  <a href={ev.tickets_url} target="_blank" rel="noreferrer"
                    className="text-xs text-blue-500 hover:underline">Tickets →</a>
                )}
                {ev.organizer && (
                  <span className="text-xs text-gray-400">by {ev.organizer}</span>
                )}
              </div>
            </div>
          </div>
        ))}
        {visible.length === 0 && (
          <p className="text-gray-400 text-center py-8">No upcoming events match this filter.</p>
        )}
      </div>
    </div>
  )
}
