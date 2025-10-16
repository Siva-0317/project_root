// app/api/login/route.ts
declare const process: { env: { BACKEND_BASE?: string } };

export async function POST(req: Request) {
  const body = await req.json();
  const r = await fetch(process.env.BACKEND_BASE + "/api/login", {
    method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(body),
  });
  return new Response(await r.text(), { headers: {"Content-Type":"application/json"} });
}

// app/api/logout/route.ts
export async function POST_logout() {
  const r = await fetch(process.env.BACKEND_BASE + "/api/logout", { method: "POST" });
  return new Response(await r.text(), { headers: {"Content-Type":"application/json"} });
}

// app/api/transcribe/route.ts
export async function POST_transcribe(req: Request) {
  const fd = await req.formData();
  const r = await fetch(process.env.BACKEND_BASE + "/api/transcribe", { method: "POST", body: fd });
  return new Response(await r.text(), { headers: {"Content-Type":"application/json"} });
}
