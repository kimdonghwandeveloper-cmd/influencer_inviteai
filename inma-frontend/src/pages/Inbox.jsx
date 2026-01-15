import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Mail, Search, RefreshCw, ChevronRight, Star, Archive, Trash2 } from 'lucide-react';
import { cn } from '../lib/utils';
import { api } from '../lib/api';

export default function Inbox() {
    const [selectedThread, setSelectedThread] = useState(null);
    const [filter, setFilter] = useState('all'); // all, unread, sent

    const { data: threads, isLoading, refetch } = useQuery({
        queryKey: ['inbox', filter],
        queryFn: async () => {
            // Mock data for immediate feedback while backend is being built
            /*
            return [
                {
                    id: '1',
                    subject: 'Re: [제안] 협업 제안드립니다',
                    snippet: '네 좋은 제안 감사합니다. 긍정적으로 검토해보겠습니다...',
                    from: 'influencer@example.com',
                    date: '2026-01-15T10:00:00Z',
                    unread: true,
                    tags: ['INMA-001']
                },
                {
                    id: '2',
                    subject: 'Re: 제품 협찬 문의',
                    snippet: '사이즈가 어떻게 되나요? 100 사이즈로 보내주실 수 있나요?',
                    from: 'creator_kim@gmail.com',
                    date: '2026-01-14T15:30:00Z',
                    unread: false,
                    tags: ['INMA-002']
                }
            ];
            */
            // Actual call (will fail 404 until backend is ready)
            const res = await api.get('/inbox');
            return res.data;
        },
        retry: false
    });

    if (isLoading) return <div className="p-8 flex justify-center"><RefreshCw className="animate-spin text-muted-foreground" /></div>;

    return (
        <div className="h-[calc(100vh-100px)] flex gap-4">
            {/* Thread List */}
            <div className="w-1/3 bg-card rounded-xl border border-border shadow-sm overflow-hidden flex flex-col">
                <div className="p-4 border-b border-border flex justify-between items-center bg-muted/30">
                    <h2 className="font-bold text-lg flex items-center gap-2">
                        <Mail size={20} />
                        Inbox
                    </h2>
                    <button onClick={() => refetch()} className="p-2 hover:bg-background rounded-full transition-colors">
                        <RefreshCw size={16} />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto">
                    {threads?.length === 0 && (
                        <div className="p-8 text-center text-muted-foreground text-sm">
                            메일이 없습니다.
                        </div>
                    )}
                    {threads?.map(thread => (
                        <div
                            key={thread.id}
                            onClick={() => setSelectedThread(thread)}
                            className={cn(
                                "p-4 border-b border-border cursor-pointer hover:bg-muted/50 transition-colors",
                                selectedThread?.id === thread.id ? "bg-primary/5 border-l-4 border-l-primary" : "border-l-4 border-l-transparent",
                                thread.unread ? "font-semibold" : "text-muted-foreground"
                            )}
                        >
                            <div className="flex justify-between items-start mb-1">
                                <span className="text-sm truncate max-w-[70%]">{thread.from}</span>
                                <span className="text-xs opacity-70">
                                    {new Date(thread.date).toLocaleDateString()}
                                </span>
                            </div>
                            <div className="text-sm font-medium mb-1 truncate">{thread.subject}</div>
                            <div className="text-xs opacity-80 truncate">{thread.snippet}</div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Thread Detail */}
            <div className="flex-1 bg-card rounded-xl border border-border shadow-sm overflow-hidden flex flex-col">
                {selectedThread ? (
                    <>
                        <div className="p-6 border-b border-border">
                            <h2 className="text-2xl font-bold mb-4">{selectedThread.subject}</h2>
                            <div className="flex justify-between items-center">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold">
                                        {selectedThread.from[0].toUpperCase()}
                                    </div>
                                    <div>
                                        <div className="font-medium text-sm">{selectedThread.from}</div>
                                        <div className="text-xs text-muted-foreground">to me</div>
                                    </div>
                                </div>
                                <div className="text-sm text-muted-foreground">
                                    {new Date(selectedThread.date).toLocaleString()}
                                </div>
                            </div>
                        </div>
                        <div className="flex-1 p-8 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                            {selectedThread.body || selectedThread.snippet}
                        </div>
                        <div className="p-4 border-t border-border bg-muted/30">
                            <textarea
                                placeholder="답장 작성..."
                                className="w-full p-4 rounded-lg border border-border focus:ring-2 focus:ring-primary/20 outline-none resize-none h-32"
                            />
                            <div className="flex justify-end mt-2">
                                <button className="bg-primary text-primary-foreground px-6 py-2 rounded-lg font-medium hover:bg-primary/90 transition">
                                    전송
                                </button>
                            </div>
                        </div>
                    </>
                ) : (
                    <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground opacity-50">
                        <Mail size={48} className="mb-4" />
                        <p>메일을 선택하여 내용을 확인하세요.</p>
                    </div>
                )}
            </div>
        </div>
    );
}
