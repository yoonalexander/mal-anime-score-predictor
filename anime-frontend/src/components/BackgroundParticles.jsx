import Particles from "@/components/Particles";

export default function BackgroundParticles() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10"
    >
      <Particles
        className="h-full w-full"
        particleColors={["#ffffff", "#d1d5db", "#9ca3af"]}
        particleCount={220}
        particleSpread={10}
        speed={0.12}
        particleBaseSize={110}
        moveParticlesOnHover={false}
        alphaParticles={false}
        disableRotation={false}
      />
      {/* Optional soft fade near the bottom for contrast */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-black/20" />
    </div>
  );
}
