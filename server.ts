import 'dotenv/config';
import express from 'express';
import axios from 'axios';
import cors from 'cors';
import path from 'path';
import { fileURLToPath } from 'url';
import { GoogleGenAI, Type, Modality } from "@google/genai";
import { Storage } from '@google-cloud/storage';
import nodemailer from 'nodemailer';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function startServer() {
    const app = express();
    const PORT = 3000;

    app.use(cors());
    app.use(express.json({ limit: '50mb' })); // Increase limit for HTML mirrors

    // Simple logger
    app.use((req, res, next) => {
        console.log(`${new Date().toISOString()} - ${req.method} ${req.url}`);
        next();
    });

    // Fetch these from Google Cloud Environment Variables
    const rawDomain = process.env.FRESHDESK_DOMAIN || 'ecomplete.freshdesk.com';
    const FRESHDESK_DOMAIN = rawDomain.includes('.') ? rawDomain : `${rawDomain}.freshdesk.com`;
    const API_KEY = process.env.FRESHDESK_API_KEY;

    if (!API_KEY) {
        console.warn("⚠️ WARNING: FRESHDESK_API_KEY environment variable is not set!");
    }

    // Format API Key for Freshdesk Authentication
    const getAuthHeader = () => 'Basic ' + Buffer.from(API_KEY + ':X').toString('base64');

    // --- SECURE PROXY ROUTES ---

    // 1. Fetch Groups
    app.get('/api/groups', async (req, res) => {
        try {
            const response = await axios.get(`https://${FRESHDESK_DOMAIN}/api/v2/groups`, {
                headers: { 'Authorization': getAuthHeader() }
            });
            res.json(response.data);
        } catch (error: any) {
            console.error("Freshdesk API Error (Groups):", error.message);
            res.status(error.response?.status || 500).json({ error: error.message });
        }
    });

    // 2. Fetch All Active Tickets (BFF Aggregation & Caching with SSE)
    let ticketsCache: { data: any[], timestamp: number } | null = null;
    const CACHE_TTL = 60 * 1000; // 1 minute cache to prevent API rate limiting

    app.get('/api/tickets/stream', async (req, res) => {
        // Establish Server-Sent Events (SSE) connection
        res.setHeader('Content-Type', 'text/event-stream');
        res.setHeader('Cache-Control', 'no-cache');
        res.setHeader('Connection', 'keep-alive');
        res.flushHeaders();

        try {
            if (ticketsCache && (Date.now() - ticketsCache.timestamp < CACHE_TTL)) {
                res.write(`data: ${JSON.stringify({ progress: 'Serving aggregated tickets from cache...', page: 0 })}\n\n`);
                res.write(`data: ${JSON.stringify({ done: true, tickets: ticketsCache.data })}\n\n`);
                return res.end();
            }

            const { updated_since } = req.query;
            let activeTickets: any[] = [];
            let page = 1;
            let keepFetching = true;

            console.log(`🔄 Starting full ticket extraction stream since ${updated_since}...`);

            while (keepFetching) {
                // Stream progress to the frontend
                res.write(`data: ${JSON.stringify({ progress: `Extracting Active Tickets (Page ${page}/40)...`, page })}\n\n`);

                let url = `https://${FRESHDESK_DOMAIN}/api/v2/tickets?per_page=100&include=stats`;
                if (page) url += `&page=${page}`;
                if (updated_since) url += `&updated_since=${encodeURIComponent(updated_since as string)}`;

                const response = await axios.get(url, {
                    headers: { 'Authorization': getAuthHeader() }
                });

                const pageData = response.data;
                
                // Filter immediately: An "Active" ticket is any ticket that is NOT Resolved (4) or Closed (5).
                const activeOnPage = pageData.filter((t: any) => t.status !== 4 && t.status !== 5);
                
                // Strip heavy fields to optimize payload size by ~70%
                const optimizedTickets = activeOnPage.map((t: any) => ({
                    id: t.id,
                    subject: t.subject,
                    status: t.status,
                    group_id: t.group_id,
                    responder_id: t.responder_id,
                    type: t.type,
                    created_at: t.created_at,
                    updated_at: t.updated_at,
                    custom_fields: t.custom_fields,
                    stats: t.stats
                }));

                activeTickets = activeTickets.concat(optimizedTickets);

                if (pageData.length < 100) keepFetching = false;
                else page++;
                
                if (page > 40) keepFetching = false; // Safety break (4000 tickets max)
            }

            console.log(`✅ Extraction complete. Found ${activeTickets.length} active tickets.`);
            
            ticketsCache = { data: activeTickets, timestamp: Date.now() };
            
            // Send final payload
            res.write(`data: ${JSON.stringify({ done: true, tickets: activeTickets })}\n\n`);
            res.end();
        } catch (error: any) {
            console.error("Freshdesk API Error (Stream):", error.message);
            res.write(`data: ${JSON.stringify({ error: error.message })}\n\n`);
            res.end();
        }
    });

    // Helper for Safe Gemini Key Loading
    const getGeminiKey = () => {
        // Try the new standard key first, then fallbacks
        const rawKey = process.env.GEMINI_API_KEY_PULSE || process.env["Gemini API Key_pulse"] || process.env.GEMINI_API_KEY || process.env.API_KEY;
        if (!rawKey) return null;
        return rawKey.trim().replace(/['"]/g, '');
    };

    // 3. AI Sentiment Analysis
    app.post('/api/ai/sentiment', async (req, res) => {
        try {
            const { tickets } = req.body;
            
            if (!tickets || !Array.isArray(tickets)) {
                return res.status(400).json({ error: "Invalid tickets array provided" });
            }

            const geminiKey = getGeminiKey();
            if (!geminiKey) {
                console.error("❌ GEMINI_API_KEY_PULSE is missing!");
                return res.status(500).json({ error: "Server configuration error: Gemini API key missing" });
            }

            const ai = new GoogleGenAI({ apiKey: geminiKey });
            
            const prompt = `
            Analyse the sentiment of the following customer support ticket subjects. 
            These are the oldest unresolved tickets in the backlog.
            
            For each ticket, determine if the customer sounds 'Frustrated', 'Neutral', or 'Positive' based purely on the subject line.
            Provide a brief 1-sentence reasoning for your classification.
            
            Tickets to analyse:
            ${JSON.stringify(tickets, null, 2)}
            `;

            const response = await ai.models.generateContent({
                model: "gemini-3-flash-preview",
                contents: prompt,
                config: {
                    responseMimeType: "application/json",
                    responseSchema: {
                        type: Type.OBJECT,
                        properties: {
                            results: {
                                type: Type.ARRAY,
                                items: {
                                    type: Type.OBJECT,
                                    properties: {
                                        id: { type: Type.INTEGER, description: "The ticket ID" },
                                        subject: { type: Type.STRING, description: "The original ticket subject" },
                                        sentiment: { type: Type.STRING, description: "Must be exactly 'Frustrated', 'Neutral', or 'Positive'" },
                                        reasoning: { type: Type.STRING, description: "A brief 1-sentence explanation of why this sentiment was chosen" }
                                    },
                                    required: ["id", "subject", "sentiment", "reasoning"]
                                }
                            }
                        },
                        required: ["results"]
                    }
                }
            });

            const resultText = response.text;
            if (!resultText) {
                throw new Error("Empty response from Gemini API");
            }

            res.json(JSON.parse(resultText));

        } catch (error: any) {
            console.error("AI Analysis Error:", error.message);
            res.status(500).json({ error: error.message });
        }
    });

    // 4. Save to Cloud (GCS) with Local Fallback
    app.post('/api/save-to-cloud', async (req, res) => {
        const { filename, content, contentType } = req.body;
        
        // Check if GCS credentials exist
        const hasGCS = process.env.GOOGLE_APPLICATION_CREDENTIALS || (process.env.GCLOUD_PROJECT && process.env.GCS_BUCKET_NAME);

        if (hasGCS) {
            try {
                const bucketName = process.env.GCS_BUCKET_NAME || 'adhoc-bkt';
                const storage = new Storage();
                const bucket = storage.bucket(bucketName);
                const file = bucket.file(filename);

                await file.save(content, {
                    contentType: contentType || 'text/plain',
                    resumable: false
                });

                return res.json({ success: true, url: `https://console.cloud.google.com/storage/browser/${bucketName}/${filename}` });
            } catch (error: any) {
                console.warn("GCS Upload failed, attempting local fallback:", error.message);
                // Proceed to fallback below
            }
        }

        // Fallback: Save locally to public/reports
        try {
            const fs = await import('fs');
            const reportsDir = path.join(__dirname, 'public', 'reports');
            
            if (!fs.existsSync(reportsDir)){
                fs.mkdirSync(reportsDir, { recursive: true });
            }
            
            const filePath = path.join(reportsDir, filename);
            fs.writeFileSync(filePath, content);
            
            // Return local URL
            const localUrl = `${req.protocol}://${req.get('host')}/reports/${filename}`;
            return res.json({ success: true, url: localUrl, local: true });
            
        } catch (localError: any) {
            console.error("Local Save Error:", localError.message);
            return res.status(500).json({ error: "Failed to save file locally." });
        }
    });

    // 5. AI Voice Briefing
    app.post('/api/ai/voice-briefing', async (req, res) => {
        try {
            const { dataSummary } = req.body;
            
            const geminiKey = getGeminiKey();
            if (!geminiKey) {
                return res.status(500).json({ error: "Server configuration error: Missing Gemini API Key." });
            }

            const ai = new GoogleGenAI({ apiKey: geminiKey });

            // Step 1: Generate the briefing script (Text)
            const scriptPrompt = `
            You are a senior customer support operations manager. 
            Write a concise, insightful, and engaging briefing script based on the following dashboard data summary.
            The script will be read aloud by a text-to-speech engine, so keep it conversational and natural.
            Highlight critical areas (especially critical aging tickets) and offer valuable encouragement.
            Keep it strictly under 150 words.
            
            Data Summary:
            ${dataSummary}
            `;

            const scriptResponse = await ai.models.generateContent({
                model: "gemini-2.5-flash",
                contents: [{ parts: [{ text: scriptPrompt }] }],
            });

            const scriptText = scriptResponse.response.text();
            if (!scriptText) {
                throw new Error("Failed to generate briefing script.");
            }

            // Step 2: Convert script to Audio (TTS)
            const ttsResponse = await ai.models.generateContent({
                model: "gemini-2.5-flash-preview-tts",
                contents: [{ parts: [{ text: scriptText }] }],
                config: {
                    responseModalities: [Modality.AUDIO],
                    speechConfig: {
                        voiceConfig: {
                            prebuiltVoiceConfig: { voiceName: 'Charon' },
                        },
                    },
                },
            });

            const base64Audio = ttsResponse.candidates?.[0]?.content?.parts?.[0]?.inlineData?.data;
            if (!base64Audio) {
                console.error("TTS Response:", JSON.stringify(ttsResponse, null, 2));
                throw new Error("Failed to generate audio from script.");
            }
            
            res.json({ audioData: base64Audio, script: scriptText });

        } catch (error: any) {
            console.error("Voice Briefing Error:", error.message);
            // Return detailed error for debugging
            res.status(500).json({ error: error.message });
        }
    });

    // 6. Fetch Single Ticket Details
    app.get('/api/tickets/:id', async (req, res) => {
        try {
            const { id } = req.params;
            const response = await axios.get(`https://${FRESHDESK_DOMAIN}/api/v2/tickets/${id}`, {
                headers: { 'Authorization': getAuthHeader() }
            });
            res.json(response.data);
        } catch (error: any) {
            console.error(`Freshdesk API Error (Ticket ${req.params.id}):`, error.message);
            res.status(error.response?.status || 500).json({ error: error.message });
        }
    });

    // 7. Send Morning Brief Email
    app.post('/api/send-morning-brief', async (req, res) => {
        try {
            const { htmlContent, subject } = req.body;
            
            if (!htmlContent) {
                return res.status(400).json({ error: "No HTML content provided." });
            }

            const SENDER_EMAIL = "taswell@ecomplete.co.za";
            const SENDER_PASS = process.env.EMAIL_PASS || "evpd vqfd vwku krkn";
            const RECIPIENT = "taswell@ecomplete.co.za";
            const todayStr = new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
            const emailSubject = subject || `CS Pulse Check – ${todayStr}`;

            // Send Email
            const transporter = nodemailer.createTransport({
                host: "smtp.gmail.com",
                port: 587,
                secure: false, // true for 465, false for other ports
                auth: {
                    user: SENDER_EMAIL,
                    pass: SENDER_PASS,
                },
            });

            const info = await transporter.sendMail({
                from: `"CS Dashboard" <${SENDER_EMAIL}>`,
                to: RECIPIENT,
                subject: emailSubject,
                html: htmlContent,
            });

            res.json({ success: true, messageId: info.messageId });

        } catch (error: any) {
            console.error("Email Brief Error:", error);
            res.status(500).json({ error: error.message });
        }
    });

    // Serve the frontend HTML files
    app.use(express.static(path.join(__dirname, 'public')));
    
    // Explicit root route
    app.get('/', (req, res) => {
        console.log("Serving root index.html");
        res.sendFile(path.join(__dirname, 'public', 'index.html'));
    });

    app.get('*', (req, res) => {
        console.log(`Fallback serving index.html for ${req.url}`);
        res.sendFile(path.join(__dirname, 'public', 'index.html'));
    });

    app.listen(PORT, '0.0.0.0', () => {
        console.log(`Server is securely running on port ${PORT}`);
    });
}

startServer().catch(err => {
    console.error("Failed to start server:", err);
});

process.on('uncaughtException', (err) => {
    console.error('Uncaught Exception:', err);
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('Unhandled Rejection at:', promise, 'reason:', reason);
});
