const COPY = {
    fr: {
        welcome: "Bonjour et bienvenue sur eGhanaVisa ! 🇬🇭\n\nJe suis **ABENA**, votre assistante virtuelle. Je suis là pour vous accompagner dans vos démarches de demande de visa pour le Ghana.\n\nJe peux vous renseigner sur les catégories de visas proposées, les documents nécessaires, les tarifs, les moyens de paiement et le suivi de votre demande.\n\nComment puis-je vous aider aujourd'hui ?",
        subtitle: "Assistante virtuelle · 24h/24",
        placeholder: "Écrivez votre question…",
        typing: "ABENA rédige une réponse…",
        error: "Désolée, je rencontre un problème technique. Veuillez réessayer ou nous contacter sur WhatsApp.",
        transferred: "Transmis à un conseiller · Ticket",
        contactTitle: "Un conseiller va vous répondre.",
        contactText: "Laissez votre e-mail (facultatif) pour recevoir sa réponse :",
        name: "Nom",
        email: "E-mail",
        done: "OK",
        open: "Ouvrir la discussion avec ABENA",
        close: "Fermer la discussion",
        send: "Envoyer",
    },
    en: {
        welcome: "Hello and welcome to eGhanaVisa! 🇬🇭\n\nI'm **ABENA**, your virtual assistant. I'm here to guide you through your Ghana visa application.\n\nI can help you with the visa categories we offer, required documents, fees, payment methods and tracking your application.\n\nHow can I help you today?",
        subtitle: "Virtual assistant · 24/7",
        placeholder: "Type your question…",
        typing: "ABENA is typing…",
        error: "Sorry, I'm having a technical issue. Please try again or contact us on WhatsApp.",
        transferred: "Transferred to an advisor · Ticket",
        contactTitle: "An advisor will get back to you.",
        contactText: "Leave your email (optional) to receive their reply:",
        name: "Name",
        email: "Email",
        done: "OK",
        open: "Open chat with ABENA",
        close: "Close chat",
        send: "Send",
    },
};

export function abenaLang() {
    const html = (document.documentElement.lang || "").toLowerCase();
    const l = html && !html.startsWith("en") ? html : (navigator.language || "en").toLowerCase();
    return l.startsWith("fr") ? "fr" : "en";
}

export function abenaCopy(lang) {
    return COPY[lang] || COPY.en;
}
