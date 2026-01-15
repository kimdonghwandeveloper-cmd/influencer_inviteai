import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, Users, Zap, Send, Inbox as InboxIcon } from 'lucide-react';
import { cn } from './lib/utils';
// Pages
import Dashboard from './pages/Dashboard';
import Influencers from './pages/Influencers';
import Matching from './pages/Matching';
import Campaigns from './pages/Campaigns';
import Inbox from './pages/Inbox';

const NavItem = ({ to, icon: Icon, label }) => {
  const location = useLocation();
  const active = location.pathname === to;
  const isExternal = to.startsWith('http');

  if (isExternal) {
    return (
      <a
        href={to}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-3 px-4 py-3 rounded-lg transition-colors hover:bg-muted text-muted-foreground hover:text-foreground"
      >
        <Icon size={20} />
        <span className="font-medium">{label}</span>
      </a>
    )
  }

  return (
    <Link to={to} className={cn(
      "flex items-center gap-3 px-4 py-3 rounded-lg transition-colors",
      active ? "bg-primary text-primary-foreground shadow-sm" : "hover:bg-muted text-muted-foreground hover:text-foreground"
    )}>
      <Icon size={20} />
      <span className="font-medium">{label}</span>
    </Link>
  )
}

function Layout({ children }) {
  return (
    <div className="flex h-screen bg-background text-foreground font-sans">
      {/* Sidebar */}
      <aside className="w-64 border-r border-border p-4 flex flex-col gap-2 bg-card">
        <div className="px-4 py-6 mb-2">
          <h1 className="text-2xl font-black tracking-tight text-primary flex items-center gap-2">
            <span className="bg-primary text-primary-foreground p-1 rounded">IN</span>
            MA
          </h1>
          <p className="text-xs text-muted-foreground mt-1 font-medium">Influencer AI Platform</p>
        </div>

        <div className="space-y-1">
          <NavItem to="/" icon={LayoutDashboard} label="대시보드" />
          <NavItem to="/influencers" icon={Users} label="인플루언서" />
          <NavItem to="/matching" icon={Zap} label="매칭" />
          <NavItem to="http://3.38.182.201:8001/" icon={Send} label="캠페인" />
          <NavItem to="/inbox" icon={InboxIcon} label="수신함" />
        </div>

        <div className="mt-auto px-4 py-4 text-xs text-muted-foreground">
          v1.0.0
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto bg-secondary/20">
        <div className="p-8 max-w-7xl mx-auto">
          {children}
        </div>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/influencers" element={<Influencers />} />
          <Route path="/matching" element={<Matching />} />
          <Route path="/campaigns" element={<Campaigns />} />
          <Route path="/inbox" element={<Inbox />} />
        </Routes>
      </Layout>
    </Router>
  )
}
