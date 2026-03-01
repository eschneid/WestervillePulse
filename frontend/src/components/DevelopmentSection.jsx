import { useState, useEffect } from "react"
import { fetchDevelopment } from "../api"

const STATUS_ORDER = ["Proposed", "Approved", "Under Construction", "Completed", "On Hold", ""]
const STATUS_COLORS = {
  "Proposed":          "bg-yellow-50 border-yellow-300",
  "Approved":          "bg-blue-50 border-blue-300",
  "Under Construction":"bg-orange-50 border-orange-300",
  "Completed":         "bg-green-50 border-green-300",
  "On Hold":           "bg-gray-50 border-gray-300",
}
const STATUS_BADGE = {
  "Proposed":          "bg-yellow-100 text-yellow-800",
  "Approved":          "bg-blue-100 text-blue-800",
  "Under Construction":"bg-orange-100 text-orange-800",
  "Completed":         "bg-green-100 text-green-800",
  "On Hold":           "bg-gray-100 text-gray-700",
}

export default function DevelopmentSection() {
  const [projects, setProjects] = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)

  useEffect(() => {
    fetchDevelopment()
      .then(setProjects)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-gray-500 py-8 text-center">Loading projects...</p>
  if (error)   return <p className="text-red-500 py-8 text-center">Error: {error}</p>

  // Group by status in defined order
  const grouped = {}
  for (const s of STATUS_ORDER) grouped[s] = []
  for (const p of projects) {
    const key = p.status && STATUS_ORDER.includes(p.status) ? p.status : ""
    grouped[key].push(p)
  }

  const activeBuckets = STATUS_ORDER.filter(s => grouped[s].length > 0)

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
      {activeBuckets.map(status => (
        <div key={status} className={`rounded-lg border-2 p-4 ${STATUS_COLORS[status] ?? "bg-gray-50 border-gray-300"}`}>
          <h3 className="font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[status] ?? "bg-gray-100 text-gray-700"}`}>
              {status || "Unknown"}
            </span>
            <span className="text-gray-400 text-sm font-normal">{grouped[status].length}</span>
          </h3>

          <div className="space-y-3">
            {grouped[status].map(p => (
              <div key={p.id} className="bg-white rounded border border-gray-200 p-3">
                <h4 className="font-medium text-gray-900 text-sm leading-snug">
                  {p.source_url
                    ? <a href={p.source_url} target="_blank" rel="noreferrer" className="hover:text-orange-600 transition-colors">{p.name}</a>
                    : p.name}
                </h4>
                {p.type && (
                  <span className="text-xs text-gray-500 mt-0.5 inline-block">{p.type}</span>
                )}
                {p.location && (
                  <p className="text-xs text-gray-400 mt-1">{p.location}</p>
                )}
                {p.description && (
                  <p className="text-xs text-gray-500 mt-1 line-clamp-3">{p.description}</p>
                )}
                {p.est_completion && (
                  <p className="text-xs text-gray-400 mt-1">Est. {p.est_completion}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
      {activeBuckets.length === 0 && (
        <p className="text-gray-400 text-center py-8 col-span-3">No development projects found.</p>
      )}
    </div>
  )
}
