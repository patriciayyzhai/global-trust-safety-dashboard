import { Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { DataProvider, useData } from './context/DataContext'
import { FilterProvider } from './context/FilterContext'
import './styles/index.css'

const HeatmapPage = lazy(() => import('./pages/HeatmapPage'))
const DatabasePage = lazy(() => import('./pages/DatabasePage'))

function Header() {
  const { loading, error, lastUpdated } = useData()

  const navItems = [
    { to: '/', label: 'Heatmap', icon: '🗺️' },
    { to: '/database', label: 'Database', icon: '📋' },
  ]

  const formatDate = (iso: string | null) => {
    if (!iso) return ''
    try {
      return new Date(iso).toLocaleString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    } catch {
      return iso
    }
  }

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🛡️</span>
            <div>
              <h1 className="text-lg font-bold text-slate-900 leading-tight">
                Global Trust &amp; Safety Dashboard
              </h1>
              <p className="text-xs text-slate-500 leading-tight">
                Global regulatory severity, China sentiment &amp; monitoring-driven obligation updates · H1 2026
              </p>
            </div>
          </div>

          <nav className="flex items-center gap-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`
                }
              >
                <span className="mr-1.5">{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>

        {(loading || error || lastUpdated) && (
          <div className="flex items-center gap-4 pb-2 text-xs">
            {loading && <span className="text-slate-500">Loading data...</span>}
            {error && <span className="text-red-600">Error: {error}</span>}
            {lastUpdated && !loading && (
              <span className="text-slate-400">
                Last updated: {formatDate(lastUpdated)}
              </span>
            )}
          </div>
        )}
      </div>
    </header>
  )
}

function Footer() {
  return (
    <footer className="bg-white border-t border-slate-200 mt-12">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-2 text-sm text-slate-500">
          <p>
            Global Trust &amp; Safety Dashboard — Global regulatory intelligence
          </p>
          <p>
            158 markets · Regulatory severity, China sentiment &amp; key obligations (H1 2026)
          </p>
        </div>
      </div>
    </footer>
  )
}

function PageFallback() {
  return (
    <div className="flex items-center justify-center min-h-[50vh] text-slate-500">
      Loading page…
    </div>
  )
}

function AppContent() {
  const { error } = useData()

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center max-w-md">
          <h2 className="text-xl font-bold text-red-600 mb-2">Failed to load data</h2>
          <p className="text-slate-600">{error}</p>
          <p className="text-sm text-slate-400 mt-4">
            Make sure the data has been merged. Run <code>python scripts/merge_data.py</code>
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header />
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-6">
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<HeatmapPage />} />
            <Route path="/database" element={<DatabasePage />} />
          </Routes>
        </Suspense>
      </main>
      <Footer />
    </div>
  )
}

export default function App() {
  return (
    <DataProvider>
      <FilterProvider>
        <BrowserRouter basename={import.meta.env.VITE_BASE_PATH || '/'}>
          <AppContent />
        </BrowserRouter>
      </FilterProvider>
    </DataProvider>
  )
}
