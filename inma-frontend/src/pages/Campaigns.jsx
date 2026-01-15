
import React, { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Send, Plus, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { cn } from '../lib/utils';
import { api } from '../lib/api';

export default function Campaigns() {
    const [formData, setFormData] = useState({
        subject: '[제안] 안녕하세요, 협업 제안드립니다.',
        body: `안녕하세요, \n\n저희는 ...브랜드입니다.\n\n귀하의 채널을 흥미롭게 보았습니다.`,
        limit: 50,
        tag_prefix: 'INMA',
        dry_run: true
    });

    const sendMutation = useMutation({
        mutationFn: async (formData) => {
            // 실제로는 /campaign/send 같은 엔드포인트 사용
            // 여기서는 /send_influencers (예시)
            const res = await api.post(`/ send_influencers`, {
                subject: formData.subject,
                body: formData.body,
                limit: parseInt(formData.limit),
                min_inma_score: parseFloat(formData.minScore),
                dry_run: false
            });
            return res.data;
        }
    });

    const handleSubmit = (e) => {
        e.preventDefault();
        sendMutation.mutate(formData);
    };

    return (
        <div className="max-w-4xl mx-auto space-y-8">
            <div>
                <h2 className="text-3xl font-bold tracking-tight mb-2">Email Campaigns</h2>
                <p className="text-muted-foreground">
                    Bulk send personalized proposals to your influencer segments.
                </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                {/* Form */}
                <div className="md:col-span-2">
                    <form onSubmit={handleSubmit} className="bg-card p-6 rounded-xl border border-border shadow-sm space-y-4">
                        <div>
                            <label className="block text-sm font-medium mb-1">Subject</label>
                            <input
                                type="text"
                                className="w-full px-4 py-2 rounded-lg bg-background border border-input focus:ring-2 focus:ring-primary/20 outline-none"
                                value={formData.subject}
                                onChange={e => setFormData({ ...formData, subject: e.target.value })}
                                required
                            />
                        </div>

                        <div>
                            <label className="block text-sm font-medium mb-1">Body Template</label>
                            <textarea
                                className="w-full h-64 px-4 py-2 rounded-lg bg-background border border-input focus:ring-2 focus:ring-primary/20 outline-none resize-none font-mono text-sm"
                                value={formData.body}
                                onChange={e => setFormData({ ...formData, body: e.target.value })}
                                required
                            />
                            <p className="text-xs text-muted-foreground mt-1 text-right">Supports basic text. HTML not supported yet.</p>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">Target Limit</label>
                                <input
                                    type="number"
                                    className="w-full px-4 py-2 rounded-lg bg-background border border-input outline-none"
                                    value={formData.limit}
                                    onChange={e => setFormData({ ...formData, limit: parseInt(e.target.value) })}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium mb-1">Tracking Tag</label>
                                <input
                                    type="text"
                                    className="w-full px-4 py-2 rounded-lg bg-background border border-input outline-none"
                                    value={formData.tag_prefix}
                                    onChange={e => setFormData({ ...formData, tag_prefix: e.target.value })}
                                />
                            </div>
                        </div>

                        <div className="flex items-center gap-2 py-2">
                            <input
                                type="checkbox"
                                id="dryRun"
                                checked={formData.dry_run}
                                onChange={e => setFormData({ ...formData, dry_run: e.target.checked })}
                                className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary"
                            />
                            <label htmlFor="dryRun" className="text-sm font-medium">Dry Run (Test Mode - No Emails Sent)</label>
                        </div>

                        <div className="pt-4 flex gap-4">
                            <button
                                type="submit"
                                disabled={sendMutation.isLoading}
                                className="flex-1 bg-primary text-primary-foreground py-2.5 rounded-lg font-bold flex items-center justify-center gap-2 hover:bg-primary/90 transition shadow-lg shadow-primary/20"
                            >
                                {sendMutation.isLoading ? <RefreshCw className="animate-spin" /> : <Send size={18} />}
                                {sendMutation.isLoading ? 'Processing...' : 'Launch Campaign'}
                            </button>
                            <button type="button" className="px-6 py-2.5 border border-border rounded-lg hover:bg-secondary transition flex items-center gap-2 font-medium">
                                <Save size={18} /> Save Draft
                            </button>
                        </div>
                    </form>
                </div>

                {/* Status / History */}
                <div>
                    <div className="bg-card p-6 rounded-xl border border-border shadow-sm h-full">
                        <h3 className="font-bold mb-4">Campaign Status</h3>

                        {sendMutation.isSuccess ? (
                            <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
                                <div className="p-4 bg-green-500/10 text-green-600 rounded-lg text-center">
                                    <div className="text-2xl font-black mb-1">Done!</div>
                                    <div className="text-sm">Processed successfully.</div>
                                </div>

                                <div className="space-y-2 text-sm">
                                    <div className="flex justify-between py-2 border-b">
                                        <span>Total Targets</span>
                                        <span className="font-bold">{sendMutation.data.total_targets}</span>
                                    </div>
                                    <div className="flex justify-between py-2 border-b">
                                        <span>Sent</span>
                                        <span className="font-bold text-green-600">{sendMutation.data.sent}</span>
                                    </div>
                                    <div className="flex justify-between py-2 border-b">
                                        <span>Failed</span>
                                        <span className="font-bold text-red-600">{sendMutation.data.failed}</span>
                                    </div>
                                </div>

                                <div className="mt-4">
                                    <h4 className="font-medium text-xs text-muted-foreground uppercase mb-2">Recent Logs</h4>
                                    <div className="bg-secondary/50 rounded-lg p-2 max-h-40 overflow-auto text-xs font-mono space-y-1">
                                        {sendMutation.data.items?.slice(0, 10).map((item, i) => (
                                            <div key={i} className="flex gap-2">
                                                <span className={item.status === 'sent' ? 'text-green-500' : 'text-yellow-500'}>
                                                    [{item.status}]
                                                </span>
                                                <span className="truncate">{item.email}</span>
                                            </div>
                                        ))}
                                        {sendMutation.data.items?.length > 10 && (
                                            <div className="text-center text-muted-foreground pt-1">...and more</div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="text-center text-muted-foreground py-10 opacity-50">
                                <div className="text-4xl mb-2">🚀</div>
                                <p>Ready to launch.</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
