import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";

const POSITIONS = [
  { left: "0%", top: "55.26%" },     // 0: Left Bottom
  { left: "0%", top: "0%" },      // 1: Left Top
  { left: "55.26%", top: "0%" },     // 2: Right Top
  { left: "55.26%", top: "55.26%" },    // 3: Right Bottom
];

export const AnimatedKanbanIcon = ({ className }: { className?: string }) => {
  const [cards, setCards] = React.useState([
    { id: 1, pos: 1 }, // Left Top
    { id: 2, pos: 0 }, // Left Bottom
    { id: 3, pos: 2 }, // Right Top
  ]);
  const [tick, setTick] = React.useState(0);
  const nextId = React.useRef(4);

  React.useEffect(() => {
    const interval = setInterval(() => {
      setTick(t => t + 1);
    }, 2500);
    return () => clearInterval(interval);
  }, []);

  React.useEffect(() => {
    if (tick === 0) return;

    if (tick % 2 !== 0) {
      // Move phase
      setCards(prev => prev.map(card => ({ ...card, pos: card.pos + 1 })).filter(card => card.pos <= 3));
    } else {
      // Spawn phase
      setCards(prev => [...prev, { id: nextId.current++, pos: 0 }]);
    }
  }, [tick]);

  return (
    <div className={`relative shrink-0 ${className || "w-[20px] h-[20px]"}`} aria-hidden="true">
      <AnimatePresence>
        {cards.map(card => (
          <motion.div
            key={card.id}
            initial={card.pos === 0 ? { left: POSITIONS[0].left, top: "110%", opacity: 0, scale: 0.5 } : false}
            animate={{ left: POSITIONS[card.pos].left, top: POSITIONS[card.pos].top, opacity: 1, scale: 1 }}
            exit={{ left: "55.26%", top: "110%", opacity: 0, scale: 0.8 }}
            transition={{
              type: card.pos === 0 ? "spring" : "tween",
              stiffness: card.pos === 0 ? 300 : undefined,
              damping: card.pos === 0 ? 20 : undefined,
              duration: card.pos === 0 ? undefined : 0.6,
              ease: card.pos === 0 ? undefined : "easeInOut"
            }}
            className={`absolute w-[8.5px] h-[8.5px] rounded-[2px] ${card.id % 4 === 0 ? 'bg-selected shadow-[0_0_6px_var(--text-selected)] z-10' : 'bg-muted'}`}
          />
        ))}
      </AnimatePresence>
    </div>
  );
};
