import { useState, useEffect } from "react"
import { fetchRestaurants } from "../api"

const TYPE_COLORS = {
  "Restaurant":     "bg-orange-100 text-orange-800",
  "Café / Coffee":  "bg-amber-100 text-amber-800",
  "Bar / Brewery":  "bg-yellow-100 text-yellow-800",
  "Retail":         "bg-pink-100 text-pink-800",
  "Fitness":        "bg-green-100 text-green-800",
  "Service":        "bg-sky-100 text-sky-800",
  "Other":          "bg-gray-100 text-gray-700",
}

const STATUS_COLORS = {
  "Now Open":      "bg-green-100 text-green-800",
  "Opening Soon":  "bg-yellow-100 text-yellow-800",
  "Closed":        "bg-red-100 text-red-800",
  "New Filing":    "bg-purple-100 text-purple-800",
}

function Stars({ rating }) {
  if (!rating) return null
  const full = Math.floor(rating)
  const half = rating - full >= 0.5
  return (
    <span className="text-yellow-400 text-sm" title={`${rating} / 5`}>
      {"★".repeat(full)}{half ? "½" : ""}{"☆".repeat(5 - full - (half ? 1 : 0))}
      <span className="text-gray-500 text-xs ml-1">{rating.toFixed(1)}</span>
    </span>
  )
}

export default function RestaurantsSection() {
  const [items, setItems]       = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [typeFilter, setType]   = useState("All")
  const [hoodFilter, setHood]   = useState("All")

  useEffect(() => {
    fetchRestaurants()
      .then(setItems)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const types = ["All", ...Array.from(new Set(items.map(i => i.type).filter(Boolean))).sort()]
  const hoods = ["All", ...Array.from(new Set(items.map(i => i.neighborhood).filter(Boolean))).sort()]

  const visible = items.filter(i =>
    (typeFilter === "All" || i.type === typeFilter) &&
    (hoodFilter === "All" || i.neighborhood === hoodFilter)
  )

  if (loading) return <p className="text-gray-500 py-8 text-center">Loading restaurants...</p>
  if (error)   return <p className="text-red-500 py-8 text-center">Error: {error}</p>

  return (
    <div>
      {/* Filters */}
      <div className="flex flex-wrap gap-4 mb-6">
        <div className="flex flex-wrap gap-2">
          {types.map(t => (
            <button key={t} onClick={() => setType(t)}
              className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                typeFilter === t ? "bg-orange-500 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}>{t}</button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {hoods.map(h => (
            <button key={h} onClick={() => setHood(h)}
              className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                hoodFilter === h ? "bg-gray-700 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}>{h}</button>
          ))}
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {visible.map(r => (
          <div key={r.id} className="bg-white rounded-lg border border-gray-200 p-4 flex flex-col gap-2">
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-semibold text-gray-900 leading-snug">
                {r.website
                  ? <a href={r.website} target="_blank" rel="noreferrer" className="hover:text-orange-600 transition-colors">{r.name}</a>
                  : r.name}
              </h3>
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap ${STATUS_COLORS[r.status] ?? "bg-gray-100 text-gray-700"}`}>
                {r.status}
              </span>
            </div>

            <div className="flex flex-wrap gap-1">
              {r.type && (
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYPE_COLORS[r.type] ?? "bg-gray-100 text-gray-700"}`}>
                  {r.type}
                </span>
              )}
              {r.neighborhood && (
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{r.neighborhood}</span>
              )}
            </div>

            {r.cuisine && <p className="text-sm text-gray-600">{r.cuisine}</p>}
            {r.rating  && <Stars rating={r.rating} />}
            {r.address && <p className="text-xs text-gray-400">{r.address}</p>}
            {r.notes   && <p className="text-xs text-gray-500 italic">{r.notes}</p>}

            {r.google_maps && (
              <a href={r.google_maps} target="_blank" rel="noreferrer"
                className="text-xs text-blue-500 hover:underline mt-auto">View on Maps →</a>
            )}
          </div>
        ))}
        {visible.length === 0 && (
          <p className="text-gray-400 text-center py-8 col-span-3">No results for this filter.</p>
        )}
      </div>
    </div>
  )
}
