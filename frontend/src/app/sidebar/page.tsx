"use client";

import { useEffect, useState, Suspense } from 'react';
import useSWR from 'swr';
import { useSearchParams } from 'next/navigation';

// Type definitions for Gorgias SDK (simplified)
declare global {
    interface Window {
        Gorgias: any;
    }
}

// Use proxy path — all API calls go through /api/backend/* which Next.js rewrites to localhost:8000
const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api/backend";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

const fetcher = (url: string, payload: any) =>
    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-API-Key': API_KEY
        },
        body: JSON.stringify(payload)
    }).then(res => res.json());

export default function SidebarContent() {
    const [ticketData, setTicketData] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const searchParams = useSearchParams();
    const ticketIdFromUrl = searchParams.get('ticket_id');

    // Organization ID - in a real app this would be determined by auth context or query param
    // Hardcoded for Phase 1 demo
    const ORG_Id = 1;

    // Initialize from URL if available
    useEffect(() => {
        if (ticketIdFromUrl && !ticketData) {
            setTicketData({
                ticket_id: ticketIdFromUrl,
                ticket_body: null,
                customer_email: null
            });
        }
    }, [ticketIdFromUrl]);

    // Initialize Gorgias Listener
    useEffect(() => {
        const initGorgias = () => {
            if (window.Gorgias) {
                window.Gorgias.on('ticket:load', (data: any) => {
                    console.log("Ticket Loaded:", data);
                    // Standardize data structure from Gorgias SDK
                    setTicketData({
                        ticket_id: data.id,
                        ticket_body: data.description || data.subject, // Fallback if description empty
                        customer_email: data.customer?.email
                    });
                });
            } else {
                // Retry or wait if SDK not ready immediately
                setTimeout(initGorgias, 1000);
            }
        };

        if (typeof window !== 'undefined') {
            initGorgias();
        }
    }, []);

    // Poll for suggestions only when ticketData is available
    const { data: suggestion, error } = useSWR(
        ticketData ? ['/api/suggestion', ticketData.ticket_id] : null,
        () => fetcher(`${API_URL}/v1/suggest`, {
            ticket_id: ticketData.ticket_id,
            ticket_body: ticketData.ticket_body,
            customer_email: ticketData.customer_email,
            org_id: ORG_Id
        }),
        {
            refreshInterval: 0, // Don't auto-poll continuously, just fetch once per ticket load usually
            revalidateOnFocus: false,
            shouldRetryOnError: false
        }
    );

    const handlePushToDraft = async (text: string) => {
        if (window.Gorgias) {
            try {
                await window.Gorgias.ticket.reply({
                    body_text: text,
                    channel: 'email' // or deduce
                });
                // Alternatively set draft
                // window.Gorgias.ticket.setDraft(text);
            } catch (e) {
                console.error("Failed to push to Gorgias", e);
                alert("Failed to push to draft. Check console.");
            }
        } else {
            alert("Gorgias SDK not found. (Are you running globally?)");
        }
    };

    const handleFeedback = async (helpful: boolean) => {
        if (!suggestion || !ticketData) return;

        try {
            await fetch(`${API_URL}/audit/log`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': API_KEY
                },
                body: JSON.stringify({
                    org_id: ORG_Id,
                    ticket_id: ticketData.ticket_id,
                    helpful: helpful,
                    feedback_text: helpful ? "Thumbs Up" : "Thumbs Down"
                }),
            });
            alert("Thanks for your feedback!");
        } catch (e) {
            console.error(e);
        }
    };

    if (!ticketData) {
        return (
            <div className="flex items-center justify-center h-screen bg-gray-50 text-gray-500 text-sm">
                Waiting for Ticket...
            </div>
        );
    }

    return (
        <div className="w-[300px] h-screen bg-white border-l border-gray-200 flex flex-col font-sans">
            {/* Header */}
            <div className="p-4 border-b border-gray-100 bg-gray-50">
                <h2 className="text-sm font-semibold text-gray-800">Smart Assist</h2>
                <p className="text-xs text-gray-500 mt-1">Powered by Universal Brain</p>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {!suggestion && !error && (
                    <div className="animate-pulse space-y-3">
                        <div className="h-4 bg-gray-200 rounded w-3/4"></div>
                        <div className="h-4 bg-gray-200 rounded w-1/2"></div>
                    </div>
                )}

                {error && (
                    <div className="p-3 bg-red-50 text-red-600 text-xs rounded border border-red-100">
                        Failed to load suggestion.
                    </div>
                )}

                {suggestion && (
                    <>
                        <div className={`p-3 rounded-lg text-sm leading-relaxed border ${suggestion.confidence_score < 0.7 ? 'bg-amber-50 border-amber-200 text-amber-900' : 'bg-blue-50 border-blue-100 text-gray-800'
                            }`}>
                            {suggestion.suggested_draft}
                        </div>

                        {suggestion.source_references?.length > 0 && (
                            <div className="mt-2">
                                <p className="text-xs font-medium text-gray-500 mb-1">Sources:</p>
                                <ul className="space-y-1">
                                    {suggestion.source_references.map((ref: string, i: number) => (
                                        <li key={i}>
                                            <a href={ref} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 hover:underline truncate block">
                                                {ref}
                                            </a>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </>
                )}
            </div>

            {/* Footer / Actions */}
            {suggestion && (
                <div className="p-4 border-t border-gray-100 bg-gray-50 space-y-3">
                    <button
                        onClick={() => handlePushToDraft(suggestion.suggested_draft)}
                        className="w-full py-2 px-4 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded shadow-sm transition-colors"
                    >
                        Push to Draft
                    </button>

                    <div className="flex justify-between items-center px-2">
                        <span className="text-xs text-gray-400">Was this helpful?</span>
                        <div className="flex space-x-2">
                            <button
                                onClick={() => handleFeedback(true)}
                                className="p-1.5 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded transition-colors"
                                aria-label="Thumbs Up"
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5" /></svg>
                            </button>
                            <button
                                onClick={() => handleFeedback(false)}
                                className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                                aria-label="Thumbs Down"
                            >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018a2 2 0 01.485.06l3.76.94m-7 10v5a2 2 0 002 2h.095c.5 0 .905-.405.905-.905 0-.714.211-1.412.608-2.006L17 13V4m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5" /></svg>
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
