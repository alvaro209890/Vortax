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
    category: "Pesquisa",
    color: "blue",
    prompt: "Pesquise as últimas notícias sobre inteligência artificial e me faça um resumo detalhado com as fontes",
    label: "Resumo de notícias sobre IA",
    detail: "Pesquisa na web + múltiplas fontes",
  },
  {
    icon: Code2,
    category: "Desenvolvimento",
    color: "green",
    prompt: "Crie um site de portfólio moderno e responsivo com HTML, CSS e JavaScript — dark mode, animações suaves e seções de projetos e contato",
    label: "Site de portfólio completo",
    detail: "HTML + CSS + JS • validação automática",
  },
  {
    icon: FileSearch,
    category: "Análise",
    color: "purple",
    prompt: "Compare os planos e preços das principais operadoras de internet fibra no Brasil em 2025 e indique o melhor custo-benefício",
    label: "Comparação de planos de internet",
    detail: "Pesquisa em múltiplas fontes + tabela",
  },
  {
    icon: Terminal,
    category: "Script",
    color: "orange",
    prompt: "Crie um script Python que monitora uma pasta e renomeia automaticamente os arquivos de imagem com data e tamanho no nome",
    label: "Script de organização de arquivos",
    detail: "Python • pronto para executar",
  },
  {
    icon: Zap,
    category: "Automação",
    color: "yellow",
    prompt: "Pesquise e compare os 5 melhores notebooks para programação com preços atuais no Brasil, incluindo prós e contras de cada um",
    label: "Comparativo de notebooks 2025",
    detail: "Pesquisa de preços + análise técnica",
  },
  {
    icon: Sparkles,
    category: "Criação",
    color: "cyan",
    prompt: "Desenvolva uma API REST completa em Python com FastAPI para gerenciar uma lista de tarefas — endpoints de CRUD, validação e documentação",
    label: "API REST com FastAPI",
    detail: "Python + FastAPI • com documentação",
  },
];

const COLOR_MAP = {
  blue:   { bg: "rgba(59, 130, 246, 0.1)",  border: "rgba(59, 130, 246, 0.2)",  icon: "#60a5fa" },
  green:  { bg: "rgba(8, 198, 93, 0.1)",    border: "rgba(8, 198, 93, 0.2)",    icon: "#08C65D" },
  purple: { bg: "rgba(168, 85, 247, 0.1)",  border: "rgba(168, 85, 247, 0.2)",  icon: "#c084fc" },
  orange: { bg: "rgba(249, 115, 22, 0.1)",  border: "rgba(249, 115, 22, 0.2)",  icon: "#fb923c" },
  yellow: { bg: "rgba(234, 179, 8, 0.1)",   border: "rgba(234, 179, 8, 0.2)",   icon: "#facc15" },
  cyan:   { bg: "rgba(6, 182, 212, 0.1)",   border: "rgba(6, 182, 212, 0.2)",   icon: "#22d3ee" },
};

export function OnboardingScreen({ onSubmit }) {
  function handleExample(prompt) {
    onSubmit(prompt, []);
  }

  return (
    <div className="onboarding-screen">
      <motion.div
        className="onboarding-hero"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
      >
        <img src="/vortax-logo.png" alt="Vortax" className="onboarding-logo" />
        <h1 className="onboarding-title">Como posso ajudar hoje?</h1>
        <p className="onboarding-subtitle">
          Pesquiso na web, crio software completo, analiso dados e opero este computador
          enquanto você acompanha tudo em tempo real.
        </p>

        <div className="onboarding-caps">
          <span><Globe size={12} /> Pesquisa com múltiplas fontes</span>
          <span><Code2 size={12} /> Desenvolvimento de software</span>
          <span><Zap size={12} /> Execução de scripts</span>
          <span><FileSearch size={12} /> Análise e comparação</span>
        </div>
      </motion.div>

      <motion.div
        className="onboarding-grid"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.12, ease: "easeOut" }}
      >
        {EXAMPLES.map((example, index) => {
          const colors = COLOR_MAP[example.color];
          const Icon = example.icon;
          return (
            <motion.button
              key={example.label}
              className="onboarding-card"
              style={{
                "--card-bg": colors.bg,
                "--card-border": colors.border,
                "--card-icon": colors.icon,
              }}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.15 + index * 0.05, ease: "easeOut" }}
              whileHover={{ y: -2, scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => handleExample(example.prompt)}
              type="button"
            >
              <div className="onboarding-card-icon">
                <Icon size={16} />
              </div>
              <div className="onboarding-card-body">
                <span className="onboarding-card-category">{example.category}</span>
                <strong className="onboarding-card-label">{example.label}</strong>
                <span className="onboarding-card-detail">{example.detail}</span>
              </div>
            </motion.button>
          );
        })}
      </motion.div>

      <p className="onboarding-hint">
        Clique em um exemplo ou escreva sua própria tarefa no campo abaixo
      </p>
    </div>
  );
}
