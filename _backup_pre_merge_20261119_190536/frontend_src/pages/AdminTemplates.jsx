import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { toast } from "sonner";
import { Save, Eye } from "lucide-react";

const TPL_ORDER = ["submitted", "in_progress", "done"];
const LANGS = ["en", "fr"];

export default function AdminTemplates() {
    const [templates, setTemplates] = useState([]);
    const [log, setLog] = useState([]);
    const [preview, setPreview] = useState(null);

    const load = async () => {
        const [t, l] = await Promise.all([api.get("/admin/email-templates"), api.get("/admin/email-log")]);
        setTemplates(t.data); setLog(l.data);
    };
    useEffect(() => { load(); }, []);

    const save = async (t) => {
        await api.post("/admin/email-templates", t);
        toast.success("Template saved"); load();
    };

    return (
        <div className="p-6 md:p-10 max-w-6xl">
            <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Command Center</div>
            <h1 className="mt-1 font-heading text-3xl font-bold">Email Templates</h1>
            <p className="mt-2 text-slate-500 text-sm">Bilingual (EN/FR). Variables: {"{{name}}, {{tracking}}, {{visa_type}}, {{processing}}, {{amount}}"}</p>

            <div className="mt-8 space-y-6">
                {TPL_ORDER.map((name) => (
                    <div key={name} className="bg-white rounded-xl border border-black/10 p-6">
                        <div className="font-heading font-semibold capitalize text-lg">{name.replace("_", " ")} email</div>
                        <div className="mt-4 grid md:grid-cols-2 gap-6">
                            {LANGS.map((lang) => {
                                const t = templates.find((x) => x.template_name === name && x.lang === lang) || { template_name: name, lang, subject: "", html: "" };
                                return <TemplateEditor key={lang} t={t} onSave={save} onPreview={() => setPreview(t)} />;
                            })}
                        </div>
                    </div>
                ))}
            </div>

            {/* Email log */}
            <div className="mt-10 bg-white rounded-xl border border-black/10 p-6">
                <div className="font-heading font-semibold">Email log (last 100)</div>
                <div className="mt-4 space-y-2 max-h-96 overflow-y-auto">
                    {log.map((e) => (
                        <div key={e.id} className="flex items-center justify-between gap-3 text-sm p-2 rounded hover:bg-slate-50 border border-transparent hover:border-black/5">
                            <div className="min-w-0 flex-1">
                                <div className="font-medium truncate">{e.subject}</div>
                                <div className="text-xs text-slate-500">{new Date(e.created_at).toLocaleString()} · {e.recipient} · {e.template_name} · {e.lang}</div>
                            </div>
                            <span className={`text-[10px] uppercase tracking-widest px-2 py-1 rounded font-bold ${e.simulated ? "bg-ghana-gold/40 text-ghana-black" : "bg-ghana-green text-white"}`}>
                                {e.simulated ? "Simulated" : "Sent"}
                            </span>
                            <button onClick={() => setPreview(e)} data-testid={`log-preview-${e.id}`} className="text-xs border border-black/10 px-2 py-1 rounded hover:bg-slate-100 inline-flex items-center gap-1"><Eye size={12} /> View</button>
                        </div>
                    ))}
                    {log.length === 0 && <div className="text-sm text-slate-500 text-center py-6">No emails yet.</div>}
                </div>
            </div>

            {preview && (
                <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 overflow-y-auto">
                    <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full my-8">
                        <div className="p-4 border-b border-black/5 flex items-center justify-between">
                            <div className="font-heading font-semibold truncate">{preview.subject}</div>
                            <button onClick={() => setPreview(null)} className="text-sm text-slate-500">Close</button>
                        </div>
                        <div className="p-4 max-h-[70vh] overflow-y-auto">
                            <iframe title="preview" srcDoc={preview.html} className="w-full h-[60vh] border-0" />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function TemplateEditor({ t, onSave, onPreview }) {
    const [subject, setSubject] = useState(t.subject);
    const [html, setHtml] = useState(t.html);
    useEffect(() => { setSubject(t.subject); setHtml(t.html); }, [t]);
    return (
        <div className="border border-black/5 rounded-lg p-4 bg-slate-50">
            <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-2">{t.lang}</div>
            <input value={subject} onChange={(e) => setSubject(e.target.value)} data-testid={`tpl-${t.template_name}-${t.lang}-subject`}
                className="w-full border border-black/10 rounded-md px-3 py-2 text-sm bg-white mb-2" placeholder="Subject" />
            <textarea value={html} onChange={(e) => setHtml(e.target.value)} data-testid={`tpl-${t.template_name}-${t.lang}-html`}
                className="w-full border border-black/10 rounded-md px-3 py-2 text-xs bg-white font-mono h-40 resize-y" />
            <div className="mt-2 flex gap-2">
                <button onClick={() => onSave({ ...t, subject, html })} data-testid={`tpl-${t.template_name}-${t.lang}-save`}
                    className="bg-ghana-green text-white px-3 py-1.5 rounded text-xs font-medium inline-flex items-center gap-1 hover:bg-ghana-green-dark"><Save size={12} /> Save</button>
                <button onClick={onPreview} className="border border-black/10 px-3 py-1.5 rounded text-xs inline-flex items-center gap-1 hover:bg-slate-50"><Eye size={12} /> Preview</button>
            </div>
        </div>
    );
}
