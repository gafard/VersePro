import { BACKEND_BASE } from "../../env.js";
export async function api(
  path,
  data,
  method = data === undefined ? "GET" : "POST",
) {
  const response = await fetch(`${BACKEND_BASE}/api/v1/${path}`, {
    method,
    ...(data !== undefined
      ? {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        }
      : {}),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok)
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : "Vérifiez les champs et réessayez.",
    );
  return result;
}
export function saveFile(name, data, type = "application/json") {
  const url = URL.createObjectURL(
    new Blob(
      [typeof data === "string" ? data : JSON.stringify(data, null, 2)],
      { type },
    ),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
export function servicePayload(data) {
  return {
    format: "versepro-service",
    schema_version: 1,
    name: data.name,
    date: data.date || "",
    notes: data.notes || "",
    references: data.references || [],
    bible_version: data.bible_version || "LSG",
    room_name: data.room_name || "",
    projection_theme: data.projection_theme || "presentation",
  };
}
