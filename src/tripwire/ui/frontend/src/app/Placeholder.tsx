import { Outlet, useLocation, useParams } from "react-router-dom";

interface PlaceholderProps {
  name: string;
}

export function Placeholder({ name }: PlaceholderProps) {
  const params = useParams();
  const location = useLocation();
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-foreground">{name}</h1>
      <p className="mt-2 text-muted-foreground">Coming in a later issue.</p>
      <pre className="mt-4 rounded bg-muted p-4 text-xs text-muted-foreground">
        {JSON.stringify({ path: location.pathname, params }, null, 2)}
      </pre>
      <Outlet />
    </div>
  );
}
