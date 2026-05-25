"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Clapperboard, Cpu, Mic2, Music2, Sparkles, Wand2 } from "lucide-react";

import { Button } from "@/components/ui/button";

const FEATURES = [
  { icon: Wand2, title: "Script → Scenes", desc: "Local LLMs (Llama 3 / Mistral / Qwen) break your script into cinematic shots." },
  { icon: Sparkles, title: "Cinematic Images", desc: "SDXL via ComfyUI with ControlNet & IPAdapter for film-grade frames." },
  { icon: Clapperboard, title: "Character Lock", desc: "Face-embedding + IPAdapter keep the same character across every scene." },
  { icon: Cpu, title: "Image → Video", desc: "AnimateDiff / Stable Video Diffusion with camera moves and transitions." },
  { icon: Mic2, title: "Voice Narration", desc: "Emotional multilingual narration via XTTS v2 & Bark." },
  { icon: Music2, title: "AI Score", desc: "Cinematic background music generated with MusicGen." },
];

export default function Landing() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* animated gradient backdrop */}
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(60%_50%_at_50%_0%,hsl(var(--primary)/0.18),transparent)]" />
      <div className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(40%_40%_at_80%_30%,hsl(var(--accent)/0.12),transparent)]" />

      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <div className="flex items-center gap-2">
          <Clapperboard className="h-6 w-6 text-primary" />
          <span className="text-lg font-bold text-gradient">Cineforge</span>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="ghost" asChild>
            <Link href="/login">Sign in</Link>
          </Button>
          <Button variant="gradient" asChild>
            <Link href="/register">Get started</Link>
          </Button>
        </div>
      </header>

      <section className="mx-auto max-w-4xl px-6 pb-20 pt-16 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
        >
          <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-muted-foreground">
            <Sparkles className="h-3 w-3 text-accent" /> 100% free & open-source · runs on free Colab/Kaggle GPU
          </span>
          <h1 className="mt-6 text-balance text-5xl font-extrabold leading-tight tracking-tight md:text-6xl">
            Turn a script into a <span className="text-gradient">cinematic film</span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-balance text-lg text-muted-foreground">
            Cineforge writes scenes, generates consistent characters, animates shots, narrates, and
            scores — then exports a finished MP4. A free alternative to RunwayML, Pika and Luma.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3">
            <Button variant="gradient" size="lg" asChild>
              <Link href="/register">
                Start creating <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button variant="outline" size="lg" asChild>
              <Link href="/login">I have an account</Link>
            </Button>
          </div>
        </motion.div>
      </section>

      <section className="mx-auto grid max-w-5xl gap-4 px-6 pb-24 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f, i) => (
          <motion.div
            key={f.title}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.05 }}
            className="glass rounded-xl p-5"
          >
            <f.icon className="h-6 w-6 text-primary" />
            <h3 className="mt-3 font-semibold">{f.title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{f.desc}</p>
          </motion.div>
        ))}
      </section>
    </div>
  );
}
