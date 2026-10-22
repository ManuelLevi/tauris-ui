// The sample data: teams, their projects and the files in them. Nothing here
// is saved; "Add files…" adds to the page's copy until it is closed.

const KB = 1024;

const TEAMS = [
  { id: "team-a", name: "Team A", projects: [
    { id: "project-a", name: "Project A", color: "#2675bf", files: [
      { id: "project-a/hello", name: "Hello.md", size: 45 * KB, added: "2026-10-12", by: "Ana", text: "# Hello\n\nThe first note of Project A. Open it in the same tab, or in a tab of its own." },
      { id: "project-a/sup", name: "Sup.txt", size: 5 * KB, added: "2026-10-14", by: "Ben", text: "Sup.\n\nThree lines of nothing much, kept for the table." },
    ] },
  ] },
  { id: "team-b", name: "Team B", projects: [
    { id: "megalomania", name: "Megalomania", color: "#b83a31", files: [
      { id: "megalomania/readme", name: "readme.md", size: 2 * KB, added: "2026-09-30", by: "Chen", text: "# Megalomania\n\nA plan that is a little too big." },
    ] },
  ] },
  { id: "team-c", name: "Team C", projects: [
    { id: "vacation-mexico", name: "Vacation Mexico", color: "#1baf7a", files: [
      { id: "vacation-mexico/places", name: "places to visit.md", size: 1 * KB, added: "2026-10-02", by: "Dia", text: "# Places to visit\n\n- Oaxaca\n- Mexico City\n- Tulum" },
    ] },
  ] },
];
