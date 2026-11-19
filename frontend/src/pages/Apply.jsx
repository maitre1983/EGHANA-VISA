import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Upload, CheckCircle2, AlertTriangle, FileText } from "lucide-react";
import api from "../lib/api";
import VisaSample from "../components/VisaSample";
import { toast } from "sonner";

const DOC_TYPES = [
    { key: "face_photo", label: "Face photo (white background, no glasses)" },
    { key: "passport_copy", label: "Passport data page copy" },
    { key: "passport_cover", label: "Passport cover" },
    { key: "flight_ticket", label: "Flight ticket or booking" },
];

export default function Apply() {
    const nav = useNavigate();
    const [config, setConfig] = useState(null);
    const [countries, setCountries] = useState({ passport: [], travel_from: [] });

    const [form, setForm] = useState({
        visa_code: "tourist_evisa",
        passport_country: "",
        passport_number: "",
        passport_type: "Ordinary",
        passport_expiry: "",
        travelling_from: "",
        arrival_date: "",
        departure_date: "",
        full_name: "",
        email: "",
        phone: "",
        profession: "",
        processing: "regular",
        lang: "en",
        // Business fields
        company_name: "",
        host_company: "",
        business_registration: "",
        business_address: "",
        purpose_of_visit: "",
    });
    const [files, setFiles] = useState({});
    const [acceptTerms, setAcceptTerms] = useState(false);
    const [acceptDeparture, setAcceptDeparture] = useState(false);
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        api.get("/config").then(({ data }) => {
            setConfig(data);
            const firstActive = (data.visa_types || []).find((v) => v.active);
            if (firstActive) setForm((f) => ({ ...f, visa_code: firstActive.code }));
        });
        api.get("/countries").then(({ data }) => setCountries(data));
    }, []);

    const activeVisaTypes = useMemo(
        () => (config?.visa_types || []).filter((v) => v.active),
        [config]
    );

    const selectedVisa = useMemo(
        () => (config?.visa_types || []).find((v) => v.code === form.visa_code),
        [config, form.visa_code]
    );
    const expressAvailable = selectedVisa?.express_available !== false;
    const priorityAvailable = selectedVisa?.priority_available !== false;
    const requiresBusinessFields = !!selectedVisa?.requires_business_fields;

    // Force regular if selected visa doesn't support express/priority
    useEffect(() => {
        if ((form.processing === "express" && !expressAvailable) ||
            (form.processing === "priority" && !priorityAvailable)) {
            setForm((f) => ({ ...f, processing: "regular" }));
        }
    }, [expressAvailable, priorityAvailable, form.processing]);

    let surcharge = 0;
    if (form.processing === "express" && expressAvailable) surcharge = config?.express_surcharge_usd || 0;
    else if (form.processing === "priority" && priorityAvailable) surcharge = config?.priority_surcharge_usd || 0;
    const total = (selectedVisa?.price_usd || 0) + surcharge;

    const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

    const setFile = (docType, file) => setFiles((old) => ({ ...old, [docType]: file }));

    const canSubmit =
        acceptTerms && acceptDeparture &&
        form.visa_code && form.passport_country && form.passport_number &&
        form.passport_expiry && form.travelling_from && form.arrival_date &&
        form.departure_date && form.full_name && form.email && form.phone && form.profession &&
        DOC_TYPES.every((d) => files[d.key]) &&
        (!requiresBusinessFields || (form.company_name && form.host_company && form.business_registration && form.purpose_of_visit));

    const submit = async () => {
        if (!canSubmit || submitting) return;
        setSubmitting(true);
        try {
            const { data } = await api.post("/applications", form);
            const tracking = data.tracking_no;
            for (const doc of DOC_TYPES) {
                const fd = new FormData();
                fd.append("doc_type", doc.key);
                fd.append("file", files[doc.key]);
                await api.post(`/applications/${tracking}/documents`, fd, { headers: { "Content-Type": "multipart/form-data" } });
            }
            nav(`/payment/${tracking}`);
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Submission failed");
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
            <div className="mb-8">
                <div className="text-xs uppercase tracking-[0.25em] text-ghana-green font-semibold">Application</div>
                <h1 className="mt-2 text-3xl md:text-4xl font-heading font-bold">Ghana eVisa &amp; ETA Application</h1>
                <p className="mt-3 text-slate-600">All fields and documents are <span className="font-semibold text-ghana-red">mandatory</span>. Documents must be JPEG, PNG or PDF (max {config?.max_upload_mb || 8} MB each).</p>
                <div className="mt-4 text-xs text-slate-500 bg-slate-50 border border-black/5 rounded-md px-3 py-2" data-testid="apply-compliance-disclaimer">
                    <strong>Independent third-party assistance:</strong> eGhanaVisa.com is not affiliated with the Government of Ghana, the Ghana Immigration Service or the Ministry of Foreign Affairs. We assist eligible travellers with Ghana Electronic Visa (eVisa) and ETA applications.
                </div>
            </div>

            <div className="grid lg:grid-cols-12 gap-8">
                {/* Left: Form */}
                <div className="lg:col-span-8 space-y-8">
                    <Section title="1. Visa & Processing">
                        <div className="grid sm:grid-cols-2 gap-4">
                            <Field label="Visa type">
                                <select data-testid="apply-visa" value={form.visa_code} onChange={(e) => set("visa_code", e.target.value)} className={selectInput}>
                                    {activeVisaTypes.map((v) => (
                                        <option key={v.code} value={v.code}>{v.name_en} — ${v.price_usd}</option>
                                    ))}
                                </select>
                            </Field>
                            <Field label="Processing speed">
                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                    <button type="button" onClick={() => set("processing", "regular")}
                                        data-testid="apply-regular"
                                        className={`p-3 rounded-md border text-left text-sm transition-colors ${form.processing === "regular" ? "border-ghana-green bg-ghana-green/5" : "border-black/10 bg-white hover:bg-slate-50"}`}>
                                        <div className="font-semibold">Regular</div>
                                        <div className="text-xs text-slate-500">{selectedVisa?.processing_time_label || "5–7 business days"} · included</div>
                                    </button>
                                    {priorityAvailable && (
                                        <button type="button" onClick={() => set("processing", "priority")}
                                            data-testid="apply-priority"
                                            className={`p-3 rounded-md border text-left text-sm transition-colors ${form.processing === "priority" ? "border-ghana-green bg-ghana-green/5" : "border-black/10 bg-white hover:bg-slate-50"}`}>
                                            <div className="font-semibold">Priority</div>
                                            <div className="text-xs text-slate-500">3 business days · +${config?.priority_surcharge_usd || 0}</div>
                                        </button>
                                    )}
                                    {expressAvailable && (
                                        <button type="button" onClick={() => set("processing", "express")}
                                            data-testid="apply-express"
                                            className={`p-3 rounded-md border text-left text-sm transition-colors ${form.processing === "express" ? "border-ghana-gold bg-ghana-gold/10" : "border-black/10 bg-white hover:bg-slate-50"}`}>
                                            <div className="font-semibold">Express</div>
                                            <div className="text-xs text-slate-500">48–72h · +${config?.express_surcharge_usd || 0}</div>
                                        </button>
                                    )}
                                </div>
                                {selectedVisa?.requires_presence && (
                                    <div className="mt-2 text-xs text-ghana-red bg-ghana-red/5 border border-ghana-red/20 rounded px-2 py-1.5" data-testid="apply-presence-warning">
                                        ⚠ Your physical presence in Ghana is required during the entire processing period.
                                    </div>
                                )}
                            </Field>
                        </div>
                    </Section>

                    <Section title="2. Passport details">
                        <div className="grid sm:grid-cols-2 gap-4">
                            <Field label="Passport country (excl. ECOWAS)">
                                <select data-testid="apply-passport-country" value={form.passport_country} onChange={(e) => set("passport_country", e.target.value)} className={selectInput}>
                                    <option value="">Select country…</option>
                                    {countries.passport.map((c) => <option key={c} value={c}>{c}</option>)}
                                </select>
                            </Field>
                            <Field label="Passport number">
                                <input data-testid="apply-passport-number" value={form.passport_number} onChange={(e) => set("passport_number", e.target.value)} className={textInput} />
                            </Field>
                            <Field label="Passport type">
                                <select data-testid="apply-passport-type" value={form.passport_type} onChange={(e) => set("passport_type", e.target.value)} className={selectInput}>
                                    <option>Ordinary</option><option>Diplomatic</option><option>Service</option><option>Other</option>
                                </select>
                            </Field>
                            <Field label="Passport expiry date">
                                <input type="date" data-testid="apply-passport-expiry" value={form.passport_expiry} onChange={(e) => set("passport_expiry", e.target.value)} className={textInput} />
                            </Field>
                        </div>
                    </Section>

                    <Section title="3. Travel details">
                        <div className="grid sm:grid-cols-2 gap-4">
                            <Field label="Travelling from">
                                <select data-testid="apply-travel-from" value={form.travelling_from} onChange={(e) => set("travelling_from", e.target.value)} className={selectInput}>
                                    <option value="">Select country…</option>
                                    {countries.travel_from.map((c) => <option key={c} value={c}>{c}</option>)}
                                </select>
                            </Field>
                            <div />
                            <Field label="Arrival date in Ghana">
                                <input type="date" data-testid="apply-arrival" value={form.arrival_date} onChange={(e) => set("arrival_date", e.target.value)} className={textInput} />
                            </Field>
                            <Field label="Departure date from Ghana">
                                <input type="date" data-testid="apply-departure" value={form.departure_date} onChange={(e) => set("departure_date", e.target.value)} className={textInput} />
                            </Field>
                        </div>
                    </Section>

                    <Section title="4. Personal details">
                        <div className="grid sm:grid-cols-2 gap-4">
                            <Field label="Full name (as in passport)">
                                <input data-testid="apply-name" value={form.full_name} onChange={(e) => set("full_name", e.target.value)} className={textInput} />
                            </Field>
                            <Field label="Email address">
                                <input type="email" data-testid="apply-email" value={form.email} onChange={(e) => set("email", e.target.value)} className={textInput} />
                            </Field>
                            <Field label="WhatsApp / phone">
                                <input data-testid="apply-phone" value={form.phone} onChange={(e) => set("phone", e.target.value)} className={textInput} />
                            </Field>
                            <Field label="Profession">
                                <input data-testid="apply-profession" value={form.profession} onChange={(e) => set("profession", e.target.value)} className={textInput} />
                            </Field>
                        </div>
                    </Section>

                    {requiresBusinessFields && (
                        <Section title="4b. Business details">
                            <div className="grid sm:grid-cols-2 gap-4">
                                <Field label="Company name">
                                    <input data-testid="apply-company-name" value={form.company_name} onChange={(e) => set("company_name", e.target.value)} className={textInput} />
                                </Field>
                                <Field label="Host company (in Ghana)">
                                    <input data-testid="apply-host-company" value={form.host_company} onChange={(e) => set("host_company", e.target.value)} className={textInput} />
                                </Field>
                                <Field label="Business registration number">
                                    <input data-testid="apply-business-reg" value={form.business_registration} onChange={(e) => set("business_registration", e.target.value)} className={textInput} />
                                </Field>
                                <Field label="Business address">
                                    <input data-testid="apply-business-address" value={form.business_address} onChange={(e) => set("business_address", e.target.value)} className={textInput} />
                                </Field>
                                <div className="sm:col-span-2">
                                    <Field label="Purpose of visit">
                                        <textarea data-testid="apply-purpose" value={form.purpose_of_visit} onChange={(e) => set("purpose_of_visit", e.target.value)} rows={2} className={textInput} />
                                    </Field>
                                </div>
                            </div>
                            <div className="mt-3 text-xs text-slate-500 bg-slate-50 border border-black/5 rounded px-3 py-2">
                                Business applications also require an <strong>Invitation Letter</strong> — upload it as one of the documents below (either as the flight ticket slot or via WhatsApp support).
                            </div>
                        </Section>
                    )}

                    <Section title="5. Documents">                        <div className="grid sm:grid-cols-2 gap-4">
                            {DOC_TYPES.map((d) => (
                                <label key={d.key} className={`border-2 border-dashed rounded-lg p-4 flex flex-col items-center justify-center text-center cursor-pointer transition-colors ${files[d.key] ? "border-ghana-green bg-ghana-green/5" : "border-black/10 bg-slate-50 hover:bg-slate-100"}`}>
                                    <input type="file" accept=".jpg,.jpeg,.png,.pdf,image/*,application/pdf" className="hidden" data-testid={`apply-file-${d.key}`}
                                        onChange={(e) => setFile(d.key, e.target.files?.[0])} />
                                    {files[d.key] ? <CheckCircle2 size={24} className="text-ghana-green" /> : <Upload size={24} className="text-slate-500" />}
                                    <div className="mt-2 font-medium text-sm">{d.label} <span className="text-ghana-red" aria-hidden="true">*</span></div>
                                    <div className="mt-1 text-xs text-slate-500">
                                        {files[d.key] ? files[d.key].name : "JPEG · PNG · PDF"}
                                    </div>
                                </label>
                            ))}
                        </div>
                    </Section>

                    {/* Departure warning + terms */}
                    <div className="rounded-xl border-2 border-ghana-red/40 bg-ghana-red/5 p-6" data-testid="apply-departure-warning">
                        <div className="flex items-start gap-3">
                            <AlertTriangle className="text-ghana-red mt-0.5" size={22} />
                            <div>
                                <div className="font-heading font-semibold text-ghana-red">Departure date compliance</div>
                                <p className="mt-2 text-sm text-slate-700 leading-relaxed">
                                    If the traveller remains in Ghana beyond the declared departure date, e.GHANA Visa Services declines <strong>all responsibility</strong>. The Ghana Immigration Service has full authority under Ghanaian law to detain, fine or deport the traveller. The traveller bears sole responsibility.
                                </p>
                            </div>
                        </div>
                    </div>

                    <div className="space-y-3">
                        <label className="flex items-start gap-3 cursor-pointer">
                            <input type="checkbox" checked={acceptTerms} onChange={(e) => setAcceptTerms(e.target.checked)} data-testid="apply-accept-terms" className="mt-1 accent-ghana-green w-4 h-4" />
                            <span className="text-sm text-slate-700">I accept the <a href="/terms" className="text-ghana-green underline">Terms &amp; Conditions</a> and the <a href="/privacy" className="text-ghana-green underline">Privacy Policy</a>.</span>
                        </label>
                        <label className="flex items-start gap-3 cursor-pointer">
                            <input type="checkbox" checked={acceptDeparture} onChange={(e) => setAcceptDeparture(e.target.checked)} data-testid="apply-accept-departure" className="mt-1 accent-ghana-red w-4 h-4" />
                            <span className="text-sm text-slate-700">I acknowledge the departure date compliance warning and accept full responsibility.</span>
                        </label>
                    </div>

                    <button
                        onClick={submit}
                        disabled={!canSubmit || submitting}
                        data-testid="apply-submit"
                        className="w-full bg-ghana-black text-white py-4 rounded-md font-heading font-semibold text-base disabled:opacity-40 disabled:cursor-not-allowed hover:bg-ghana-black/90 transition-colors"
                    >
                        {submitting ? "Submitting…" : `Continue to payment · $${total}`}
                    </button>
                </div>

                {/* Right: Sticky Summary */}
                <div className="lg:col-span-4">
                    <div className="sticky top-24 space-y-6">
                        <div className="bg-white/80 backdrop-blur-xl border border-black/10 rounded-xl p-6 shadow-sm" data-testid="apply-summary">
                            <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Live summary</div>
                            <h3 className="mt-2 font-heading text-xl font-semibold">{selectedVisa?.name_en || "Select a visa"}</h3>
                            <div className="mt-4 space-y-2 text-sm">
                                <Row label="Base price" value={`$${selectedVisa?.price_usd || 0}`} />
                                <Row label="Processing" value={
                                    form.processing === "express" ? "Express 48–72h" :
                                    form.processing === "priority" ? "Priority 3d" :
                                    `Regular · ${selectedVisa?.processing_time_label || "5–7d"}`
                                } />
                                <Row label="Surcharge" value={`+$${surcharge}`} />
                                <div className="border-t border-black/5 my-3" />
                                <Row label="Total" value={`$${total}`} bold />
                            </div>
                        </div>
                        <VisaSample
                            name={form.full_name}
                            passport={form.passport_number}
                            arrival={form.arrival_date}
                            departure={form.departure_date}
                            visaType={selectedVisa?.name_en?.toUpperCase()}
                        />
                        <div className="text-xs text-slate-500 flex items-start gap-2">
                            <FileText size={14} className="mt-0.5" />
                            <span data-testid="visa-sample-note">This is an illustrative visa preview only. eGhanaVisa assists travelers with submitting visa applications to the competent Ghanaian authorities. All visa approvals and issuances are determined exclusively by those authorities.</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

const textInput = "w-full rounded-md border border-black/10 px-3 py-2.5 text-sm bg-white focus:border-ghana-green focus:ring-1 focus:ring-ghana-green outline-none transition-shadow";
const selectInput = textInput;

const Section = ({ title, children }) => (
    <section className="bg-white rounded-xl border border-black/10 p-6 shadow-sm">
        <h2 className="font-heading text-lg font-semibold mb-4">{title}</h2>
        {children}
    </section>
);
const Field = ({ label, children }) => (
    <div>
        <label className="text-xs font-medium text-slate-600 uppercase tracking-wider flex items-center gap-1">
            {label} <span className="text-ghana-red" aria-hidden="true">*</span>
        </label>
        <div className="mt-1.5">{children}</div>
    </div>
);
const Row = ({ label, value, bold }) => (
    <div className="flex items-center justify-between">
        <span className="text-slate-600">{label}</span>
        <span className={`font-heading ${bold ? "text-lg font-bold text-ghana-green" : "font-medium"}`}>{value}</span>
    </div>
);
