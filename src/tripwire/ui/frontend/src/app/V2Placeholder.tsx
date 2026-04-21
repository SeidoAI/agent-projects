interface V2PlaceholderProps {
  feature: string;
}

export function V2Placeholder({ feature }: V2PlaceholderProps) {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-foreground">{feature}</h1>
      <p className="mt-2 text-muted-foreground">
        Coming in v2 — requires <code className="text-primary">tripwire.containers</code>.
      </p>
    </div>
  );
}
