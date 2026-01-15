import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import axios from 'axios';
import { Search, Zap, CheckCircle, AlertCircle } from 'lucide-react';
import { cn } from '../lib/utils';

const API_URL = 'http://localhost:8000';

export default function Matching() {
    const [selectedProduct, setSelectedProduct] = useState(null);

    // 1. Fetch Products
    const { data: products } = useQuery({
        queryKey: ['products'],
        queryFn: async () => {
            const res = await axios.get(`${API_URL}/products`);
            return res.data;
        }
    });

    // 2. Match Mutation
    const matchMutation = useMutation({
        mutationFn: async (productId) => {
            const res = await axios.post(`${API_URL}/match`, { product_id: productId, limit: 10 });
            return res.data;
        }
    });

    const handleMatch = () => {
        if (!selectedProduct) return;
        matchMutation.mutate(selectedProduct._id);
    };

    return (
        <div className="space-y-8">
            <div>
                <h2 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-yellow-500 to-orange-600 bg-clip-text text-transparent">
                    AI Product Matching
                </h2>
                <p className="text-muted-foreground mt-1">
                    Select a product to find the perfect influencers using Vector Search & AI Analysis.
                </p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Left: Product Selection */}
                <div className="lg:col-span-1 space-y-4">
                    <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
                        <h3 className="font-semibold mb-4 flex items-center gap-2">
                            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
                                📦
                            </div>
                            Select Product
                        </h3>

                        <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2 custom-scrollbar">
                            {products?.map(prod => (
                                <div
                                    key={prod._id}
                                    onClick={() => setSelectedProduct(prod)}
                                    className={cn(
                                        "p-3 rounded-lg border cursor-pointer transition-all hover:bg-muted",
                                        selectedProduct?._id === prod._id
                                            ? "border-primary bg-primary/5 ring-1 ring-primary"
                                            : "border-border"
                                    )}
                                >
                                    <div className="font-medium">{prod.title || prod.name}</div>
                                    <div className="text-xs text-muted-foreground mt-1 flex justify-between">
                                        <span>{prod.brand}</span>
                                        <span>{prod.price?.toLocaleString()} KRW</span>
                                    </div>
                                </div>
                            ))}
                        </div>

                        <button
                            onClick={handleMatch}
                            disabled={!selectedProduct || matchMutation.isLoading}
                            className="w-full mt-6 bg-gradient-to-r from-yellow-500 to-orange-500 text-white py-3 rounded-xl font-bold shadow-lg shadow-orange-500/20 hover:shadow-orange-500/40 hover:-translate-y-0.5 transition-all disabled:opacity-50 disabled:translate-y-0"
                        >
                            {matchMutation.isLoading ? 'Analyzing...' : 'Find Matches ⚡'}
                        </button>
                    </div>
                </div>

                {/* Right: Results */}
                <div className="lg:col-span-2">
                    {matchMutation.isIdle && !matchMutation.data && (
                        <div className="h-full flex flex-col items-center justify-center text-muted-foreground p-12 border-2 border-dashed border-border rounded-xl bg-secondary/20">
                            <Zap size={48} className="mb-4 opacity-50" />
                            <p>Select a product and click "Find Matches" to see AI recommendations.</p>
                        </div>
                    )}

                    {matchMutation.isError && (
                        <div className="p-4 bg-destructive/10 text-destructive rounded-xl border border-destructive/20 flex items-center gap-2">
                            <AlertCircle size={20} />
                            <span>Failed to analyze matches. Please try again.</span>
                        </div>
                    )}

                    {matchMutation.data && (
                        <div className="space-y-4">
                            <div className="flex justify-between items-center mb-2">
                                <h3 className="font-bold text-xl">Top {matchMutation.data.length} Recommendations</h3>
                                <span className="text-xs text-muted-foreground px-2 py-1 bg-secondary rounded">AI Confidence Sorted</span>
                            </div>

                            <div className="grid gap-4">
                                {matchMutation.data.map((item, idx) => (
                                    <MatchCard key={idx} item={item} rank={idx + 1} />
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function MatchCard({ item, rank }) {
    const { influencer, score, details } = item;

    return (
        <div className="bg-card border border-border p-4 rounded-xl flex flex-col md:flex-row gap-4 items-center hover:shadow-md transition-shadow relative overflow-hidden">
            {/* Rank Badge */}
            <div className="absolute top-0 left-0 bg-primary text-primary-foreground text-xs font-bold px-2 py-1 rounded-br-lg z-10">
                #{rank}
            </div>

            {/* Score Ring */}
            <div className="relative w-20 h-20 flex-shrink-0 flex items-center justify-center">
                <svg className="w-full h-full transform -rotate-90">
                    <circle cx="40" cy="40" r="36" stroke="currentColor" strokeWidth="8" fill="transparent" className="text-secondary" />
                    <circle cx="40" cy="40" r="36" stroke="currentColor" strokeWidth="8" fill="transparent"
                        strokeDasharray={226}
                        strokeDashoffset={226 - (226 * score)} // Score 0.0 - 1.0
                        className={cn(
                            "text-primary transition-all duration-1000 ease-out",
                            score > 0.8 ? "text-green-500" : score > 0.6 ? "text-yellow-500" : "text-orange-500"
                        )}
                    />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center font-black text-lg">
                    {(score * 100).toFixed(0)}
                </div>
            </div>

            <div className="flex-1 text-center md:text-left">
                <h4 className="font-bold text-lg">{influencer.title}</h4>
                <div className="flex flex-wrap gap-x-4 gap-y-1 justify-center md:justify-start text-sm text-muted-foreground mt-1">
                    <span>Subs: {(influencer.stats?.subscribers / 10000).toFixed(1)}만</span>
                    <span>Category: {details.industry}</span>
                    <span>ER: {details.er_score}</span>
                </div>
                {/* Match Reasons */}
                <div className="mt-3 flex flex-wrap gap-2 justify-center md:justify-start">
                    {details.matched_category && (
                        <span className="text-[10px] px-2 py-1 bg-green-500/10 text-green-600 rounded-full font-medium flex items-center gap-1">
                            <CheckCircle size={10} /> Category Match
                        </span>
                    )}
                    <span className="text-[10px] px-2 py-1 bg-blue-500/10 text-blue-600 rounded-full font-medium">
                        Keyword Overlap: {details.keyword_overlap}
                    </span>
                    <span className="text-[10px] px-2 py-1 bg-purple-500/10 text-purple-600 rounded-full font-medium">
                        Semantic Sim: {details.similarity}
                    </span>
                </div>
            </div>

            <button className="px-5 py-2 rounded-lg border border-primary text-primary hover:bg-primary hover:text-primary-foreground font-medium transition-colors text-sm">
                Select
            </button>
        </div>
    )
}
