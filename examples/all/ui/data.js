// The sample data: teams, their projects and the files in them (and each
// project's edits a week, the last six weeks). Nothing here is saved; "Add
// files…" adds to the page's copy until it is closed.

// How many files the sample's plan holds (Home's capacity bar).
const MAX_FILES = 12;

const KB = 1024;

const TEAMS = [
  { id: "team-a", name: "Team A", projects: [
    { id: "project-a", name: "Project A", color: "#2675bf", activity: [3, 5, 4, 8, 6, 9], files: [
      { id: "project-a/hello", name: "Hello.md", size: 45 * KB, added: "2026-10-12", by: "Ana", text: "# Hello\n\nThe first note of Project A. Open it in the same tab, or in a tab of its own." },
      { id: "project-a/sup", name: "Sup.txt", size: 5 * KB, added: "2026-10-14", by: "Ben", text: "Sup.\n\nThree lines of nothing much, kept for the table." },
    ] },
  ] },
  { id: "team-b", name: "Team B", projects: [
    { id: "megalomania", name: "Megalomania", color: "#b83a31", activity: [9, 7, 8, 4, 3, 2], files: [
      { id: "megalomania/readme", name: "readme.md", size: 2 * KB, added: "2026-09-30", by: "Chen", text: "# Megalomania\n\nA plan that is a little too big." },
    ] },
  ] },
  { id: "team-c", name: "Team C", projects: [
    { id: "vacation-mexico", name: "Vacation Mexico", color: "#1baf7a", activity: [0, 1, 1, 2, 4, 7], files: [
      { id: "vacation-mexico/places", name: "places to visit.md", size: 1 * KB, added: "2026-10-02", by: "Dia", text: "# Places to visit\n\n- Oaxaca\n- Mexico City\n- Tulum" },
    ] },
  ] },
];
