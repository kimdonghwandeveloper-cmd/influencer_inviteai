import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { Search, Filter, Mail, Users, Star, BarChart3, Youtube } from 'lucide-react';
import { cn } from '../lib/utils';
import { api } from '../lib/api';

export default function Influencers() {
    const [page, setPage] = useState(1);
    const [search, setSearch] = useState('');
    const [category, setCategory] = useState('All');

    const { data, isLoading, isError } = useQuery({
        queryKey: ['influencers', page, search, category],
        queryFn: async () => {
            const res = await api.get(`/influencers`, {
                params: { page, limit: 12, search, category }
            });
            return res.data;
        },
        keepPreviousData: true,
    });

    const categories = ["All", "IT", "Beauty", "Fashion", "Game", "Kids", "Living", "Food"];

    return (
        <div className="space-y-6">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-primary to-blue-600 bg-clip-text text-transparent">
                        Influencer Discovery
                    </h2>
                    <p className="text-muted-foreground mt-1">
                        Search and manage your influencer network.
                    </p>
                </div>

                <div className="flex gap-2">
                    <button className="bg-primary text-primary-foreground px-4 py-2 rounded-lg font-medium shadow hover:bg-primary/90 transition">
                        Add New
                    </button>
                </div>
            </div>

            {/* Filters */}
            <div className="flex flex-col md:flex-row gap-4 bg-card p-4 rounded-xl border border-border/50 shadow-sm backdrop-blur-sm">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground h-4 w-4" />
                    <input
                        type="text"
                        placeholder="Search by name, email or tag..."
                        className="w-full pl-10 pr-4 py-2 rounded-lg bg-secondary/50 border-none focus:ring-2 focus:ring-primary/20 outline-none transition-all"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                </div>
                <div className="flex gap-2 items-center overflow-x-auto pb-2 md:pb-0 hide-scrollbar">
                    {categories.map((cat) => (
                        <button
                            key={cat}
                            onClick={() => setCategory(cat)}
                            className={cn(
                                "px-4 py-2 rounded-full text-sm font-medium whitespace-nowrap transition-all",
                                category === cat
                                    ? "bg-primary text-primary-foreground shadow-md scale-105"
                                    : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
                            )}
                        >
                            {cat}
                        </button>
                    ))}
                </div>
            </div>

            {/* Grid */}
            {isLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {[...Array(6)].map((_, i) => (
                        <div key={i} className="h-64 rounded-xl bg-card animate-pulse border border-border" />
                    ))}
                </div>
            ) : isError ? (
                <div className="text-center py-20 text-destructive">
                    Failed to load data. Ensure backend is running.
                </div>
            ) : (
                <>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {data?.items?.map((inf) => (
                            <InfluencerCard key={inf._id} influencer={inf} />
                        ))}
                    </div>

                    {data?.items?.length === 0 && (
                        <div className="text-center py-20 text-muted-foreground">
                            No influencers found matching your criteria.
                        </div>
                    )}

                    {/* Pagination */}
                    <div className="flex justify-center gap-2 mt-8">
                        <button
                            disabled={page === 1}
                            onClick={() => setPage(page - 1)}
                            className="px-4 py-2 rounded-lg bg-secondary disabled:opacity-50"
                        >
                            Previous
                        </button>
                        <span className="px-4 py-2 font-medium">Page {page}</span>
                        <button
                            disabled={data?.items?.length < 12} // Simple check, ideally use total pages
                            onClick={() => setPage(page + 1)}
                            className="px-4 py-2 rounded-lg bg-secondary disabled:opacity-50"
                        >
                            Next
                        </button>
                    </div>
                </>
            )}
        </div>
    );
}

function InfluencerCard({ influencer }) {
    const stats = influencer.stats || {};
    const subscribers = stats.subscribers ? (stats.subscribers / 10000).toFixed(1) + '만' : 'N/A';
    const avgViews = stats.avg_views ? (stats.avg_views / 1000).toFixed(1) + 'K' : 'N/A';
    const cycle = stats.upload_cycle ? `${stats.upload_cycle}일` : 'N/A';
    const score = influencer.inma_score || 0;

    return (
        <div className="group bg-card hover:bg-card/80 border border-border hover:border-primary/50 rounded-xl p-5 transition-all duration-300 hover:shadow-lg hover:-translate-y-1 relative overflow-hidden">
            <div className="absolute top-0 right-0 p-3 opacity-10 group-hover:opacity-20 transition-opacity">
                <Youtube size={64} />
            </div>

            <div className="flex justify-between items-start mb-4 relative z-10">
                <div>
                    <h3 className="font-bold text-lg line-clamp-1">{influencer.title}</h3>
                    <p className="text-xs text-muted-foreground line-clamp-1">{influencer.description}</p>
                </div>
                <div className="flex flex-col items-end">
                    <span className="text-2xl font-black text-primary">{score.toFixed(1)}</span>
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold">Score</span>
                </div>
            </div>

            <div className="grid grid-cols-3 gap-2 mb-4">
                <div className="bg-secondary/50 p-2 rounded-lg text-center">
                    <Users className="w-4 h-4 mx-auto mb-1 text-blue-500" />
                    <div className="text-sm font-bold">{subscribers}</div>
                    <div className="text-[10px] text-muted-foreground">Subs</div>
                </div>
                <div className="bg-secondary/50 p-2 rounded-lg text-center">
                    <BarChart3 className="w-4 h-4 mx-auto mb-1 text-green-500" />
                    <div className="text-sm font-bold">{avgViews}</div>
                    <div className="text-[10px] text-muted-foreground">Avg Views</div>
                </div>
                <div className="bg-secondary/50 p-2 rounded-lg text-center">
                    <div className="w-4 h-4 mx-auto mb-1 font-bold text-orange-500 flex items-center justify-center text-xs">📅</div>
                    <div className="text-sm font-bold">{cycle}</div>
                    <div className="text-[10px] text-muted-foreground">Cycle</div>
                </div>
            </div>

            <div className="flex flex-wrap gap-1 mb-4 h-12 overflow-hidden">
                {/* Hashtags removed as per user request */}
            </div>

            <div className="flex gap-2">
                <button className="flex-1 flex items-center justify-center gap-2 bg-primary text-primary-foreground py-2 rounded-lg text-sm font-medium hover:bg-primary/90 transition-colors">
                    <Mail size={14} /> Contact
                </button>
            </div>
        </div>
    )
}
