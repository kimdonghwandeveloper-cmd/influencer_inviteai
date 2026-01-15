import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Users, ShoppingBag, Mail, BarChart3, TrendingUp, RefreshCw } from 'lucide-react';
import { cn } from '../lib/utils';
import { api } from '../lib/api';

export default function Dashboard() {
    const { data: stats, isLoading, isError, refetch } = useQuery({
        queryKey: ['stats'],
        queryFn: async () => {
            const res = await api.get(`/stats`);
            return res.data;
        }
    });

    if (isLoading) return <div className="p-8"><div className="animate-pulse h-8 bg-gray-200 w-1/4 rounded mb-8"></div><div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4"><div className="h-32 bg-gray-200 rounded"></div><div className="h-32 bg-gray-200 rounded"></div><div className="h-32 bg-gray-200 rounded"></div><div className="h-32 bg-gray-200 rounded"></div></div></div>;

    if (isError) return (
        <div className="p-8 flex flex-col items-center justify-center h-[50vh] text-center">
            <div className="text-destructive mb-4 text-lg font-bold">데이터를 불러오지 못했습니다.</div>
            <button onClick={() => refetch()} className="px-4 py-2 bg-primary text-primary-foreground rounded-lg flex items-center gap-2">
                <RefreshCw size={16} /> 다시 시도
            </button>
        </div>
    );

    return (
        <div className="space-y-8">
            <div>
                <h2 className="text-3xl font-bold tracking-tight">대시보드</h2>
                <p className="text-muted-foreground">INMA 플랫폼 현황 한눈에 보기</p>
            </div>

            {/* Top Stats */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <StatCard
                    title="총 인플루언서"
                    value={stats.total_influencers.toLocaleString()}
                    icon={Users}
                    color="text-blue-500"
                    bgColor="bg-blue-500/10"
                />
                <StatCard
                    title="등록된 제품"
                    value={stats.total_products.toLocaleString()}
                    icon={ShoppingBag}
                    color="text-orange-500"
                    bgColor="bg-orange-500/10"
                />
                <StatCard
                    title="이메일 발송됨"
                    value={stats.emails_sent.toLocaleString()}
                    icon={Mail}
                    color="text-green-500"
                    bgColor="bg-green-500/10"
                />
                <StatCard
                    title="활성 캠페인"
                    value={stats.active_campaigns}
                    icon={TrendingUp}
                    color="text-purple-500"
                    bgColor="bg-purple-500/10"
                />
            </div>

            {/* Charts / Activity */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                <div className="col-span-4 bg-card rounded-xl border border-border shadow-sm p-6">
                    <h3 className="font-semibold mb-4 flex items-center gap-2">
                        <BarChart3 size={20} className="text-muted-foreground" />
                        주요 키워드 트렌드
                    </h3>
                    <div className="space-y-4">
                        {stats.segments?.map((seg, idx) => (
                            <div key={idx} className="space-y-1">
                                <div className="flex justify-between text-sm">
                                    <span className="font-medium">#{seg.name}</span>
                                    <span className="text-muted-foreground">{seg.value}명</span>
                                </div>
                                <div className="h-2 bg-secondary rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-primary"
                                        style={{ width: `${(seg.value / stats.total_influencers) * 100 * 5}%` }} // Scale up for visibility
                                    />
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="col-span-3 bg-card rounded-xl border border-border shadow-sm p-6">
                    <h3 className="font-semibold mb-4">최근 알림</h3>
                    <div className="space-y-4">
                        <div className="flex items-start gap-4 p-3 bg-secondary/30 rounded-lg">
                            <div className="w-2 h-2 mt-2 rounded-full bg-green-500 shrink-0" />
                            <div>
                                <p className="text-sm font-medium">새로운 매칭 완료</p>
                                <p className="text-xs text-muted-foreground">Logitech G Pro X 제품에 대한 인플루언서 16명을 찾았습니다.</p>
                                <div className="text-[10px] text-muted-foreground mt-1">2분 전</div>
                            </div>
                        </div>
                        <div className="flex items-start gap-4 p-3 bg-secondary/30 rounded-lg">
                            <div className="w-2 h-2 mt-2 rounded-full bg-blue-500 shrink-0" />
                            <div>
                                <p className="text-sm font-medium">이메일 캠페인 시작</p>
                                <p className="text-xs text-muted-foreground">"신제품 런칭 제안" 캠페인 발송이 시작되었습니다.</p>
                                <div className="text-[10px] text-muted-foreground mt-1">1시간 전</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function StatCard({ title, value, icon: Icon, color, bgColor }) {
    return (
        <div className="p-6 bg-card rounded-xl border border-border shadow-sm flex items-center space-x-4 hover:shadow-md transition-shadow">
            <div className={cn("p-3 rounded-full", bgColor, color)}>
                <Icon size={24} />
            </div>
            <div>
                <p className="text-sm font-medium text-muted-foreground">{title}</p>
                <h3 className="text-2xl font-bold">{value}</h3>
            </div>
        </div>
    )
}
