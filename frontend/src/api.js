const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

export const fetchNews         = () => fetch(`${BASE}/api/news`).then(r => r.json())
export const fetchRestaurants  = () => fetch(`${BASE}/api/restaurants`).then(r => r.json())
export const fetchEvents       = () => fetch(`${BASE}/api/events`).then(r => r.json())
export const fetchDevelopment  = () => fetch(`${BASE}/api/development`).then(r => r.json())
