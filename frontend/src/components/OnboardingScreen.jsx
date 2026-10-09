import { motion } from "framer-motion";
import {
  Code2,
  FileSearch,
  Globe,
  Sparkles,
  Terminal,
  Zap,
} from "lucide-react";

const EXAMPLES = [
  {
    icon: Globe,
    prompt: "Pesquise as últimas notícias sobre inteligência artificial e me faça um resumo detalhado com as fontes",
    label: "Resumo de notícias de IA",
  },
  {
    icon: Code2,
    prompt: "Crie um site de portfólio moderno e responsivo com HTML, CSS e JavaScript — dark mode, animações suaves e seções de projetos e contato",
    label: "Site de portfólio",
  },
  {
    icon: FileSearch,
    prompt: "Compare os planos e preços das principais operadoras de internet fibra no Brasil e indique o melhor custo-benefício",
    label: "Comparar planos de internet",
  },
  {
    icon: Terminal,
    prompt: "Crie um script Python que monitora uma pasta e renomeia automaticamente os arquivos de imagem com data e tamanho no nome",
    label: "Script de organização",
  },
  {
    icon: Zap,
    prompt: "Pesquise e compare os 5 melhores notebooks para programação com preços atuais no Brasil, incluindo prós e contras de cada um",
    label: "Comparativo de notebooks",
  },
  {
    icon: Sparkles,
    prompt: "Desenvolva uma API REST completa em Python com FastAPI para gerenciar uma lista de tarefas — endpoints de CRUD, validação e documentação",
    label: "API REST com FastAPI",
  },
];

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Bom dia";
  if (hour < 18) return "Boa tarde";
  return "Boa noite";
}

export function OnboardingScreen({ composer, onSubmit }) {
  return (
    <div className="onboarding-screen">
      <motion.div
        className="onboarding-hero"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: "easeOut" }}
      >
        <h1 className="onboarding-title">{greeting()}!</h1>
        <p className="onboarding-subtitle">O que posso fazer por você?</p>
      </motion.div>

      <motion.div
        className="onboarding-composer"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, delay: 0.06, ease: "easeOut" }}
      >
        {composer}
      </motion.div>

      <motion.div
        className="onboarding-chips"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.35, delay: 0.14, ease: "easeOut" }}
      >
        {EXAMPLES.map(({ icon: Icon, label, prompt }) => (
          <button
            className="onboarding-chip"
            key={label}
            onClick={() => onSubmit(prompt, [])}
            title={prompt}
            type="button"
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
      </motion.div>
    </div>
  );
}
