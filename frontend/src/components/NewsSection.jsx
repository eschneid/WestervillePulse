import { useState, useEffect } from "react"
import { fetchNews } from "../api"

const SOURCE_COLORS = {
  "The Westerville News": "bg-blue-100 text-blue-800",
  "Google News":          "bg-gray-100 text-gray-700",
  "Google News (Local Gov)": "bg-purple-100 text-purple-800",
  "NBC4":  "bg-red-100 text-red-800",
  "ABC6":  "bg-yellow-100 text-yellow-800",
  "10TV":  "bg-green-100 text-green-800",
}

function formatDate(iso) {
  if (!iso) return ""
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
}

export default function NewsSection() {
  const [articles, setArticles] = useState([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [filter, setFilter]     = useState("All")

  useEffect(() => {
    fetchNews()
      .then(setArticles)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const categories = ["All", ...Array.from(new Set(articles.flatMap(a => a.categories))).sort()]
  const visible = filter === "All" ? articles : articles.filter(a => a.categories.includes(filter))

  if (loading) return <p className="text-gray-500 py-8 text-center">Loading news...</p>
  if (error)   return <p className="text-red-500 py-8 text-center">Error: {error}</p>

  return (
    <div>
      {/* Category filter */}
      <div className="flex flex-wrap gap-2 mb-6">
        {categories.map(cat => (
          <button
            key={cat}
            onClick={() => setFilter(cat)}
            className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
              filter === cat
                ? "bg-blue-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Article list */}
      <div className="space-y-4">
        {visible.map(a => (
          <div key={a.id} className="bg-white rounded-lg border border-gray-200 p-4 hover:border-blue-300 transition-colors">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${SOURCE_COLORS[a.source] ?? "bg-gray-100 text-gray-700"}`}>
                {a.source}
              </span>
              {a.categories.map(c => (
                <span key={c} className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full">{c}</span>
              ))}
              <span className="text-xs text-gray-400 ml-auto">{formatDate(a.published_date)}</span>
            </div>
            <a
              href={a.url}
              target="_blank"
              rel="noreferrer"
              className="text-gray-900 font-semibold hover:text-blue-600 transition-colors leading-snug"
            >
              {a.title}
            </a>
            {a.summary && (
              <p className="text-gray-500 text-sm mt-2 leading-relaxed">{a.summary}</p>
            )}
          </div>
        ))}
        {visible.length === 0 && (
          <p className="text-gray-400 text-center py-8">No articles in this category.</p>
        )}
      </div>
    </div>
  )
}
