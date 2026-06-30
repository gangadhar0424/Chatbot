export default async function Home() {
  let message = "Backend not reachable — make sure it is running on port 3001.";
  try {
    const res = await fetch("http://localhost:3001/api/hello", {
      cache: "no-store",
    });
    if (res.ok) {
      const data = (await res.json()) as { message: string };
      message = data.message;
    }
  } catch {
    // backend not started yet
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-2xl font-bold">Hello from Next.js</h1>
      <p className="text-slate-700">
        Backend says: <span className="font-medium">{message}</span>
      </p>
      <p className="max-w-lg text-sm text-slate-400">
        Run{" "}
        <code className="rounded bg-slate-100 px-1">npm install {"&&"} npm run dev</code>{" "}
        in <code className="rounded bg-slate-100 px-1">frontend/</code> and{" "}
        <code className="rounded bg-slate-100 px-1">npm install {"&&"} npm run dev</code>{" "}
        in <code className="rounded bg-slate-100 px-1">backend/</code> to get
        started.
      </p>
    </main>
  );
}
