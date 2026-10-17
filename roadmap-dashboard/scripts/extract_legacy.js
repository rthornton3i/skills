#!/usr/bin/env node
// extract_legacy.js <legacy-roadmap.html>
// Prints {phases, agents, features, stories, storyDetails, storyUsage} of the old single-file
// roadmap page as JSON. It takes the script text between "<script>\n(function(){" and the line
// containing "RENDER ENGINE" (that section only declares data) and runs it inside a function in a
// node vm sandbox; nothing from the page's DOM is used.
"use strict";
const fs = require("fs");
const vm = require("vm");

const file = process.argv[2];
if (!file) {
  console.error("usage: node extract_legacy.js <legacy-roadmap.html>");
  process.exit(2);
}
const html = fs.readFileSync(file, "utf8");
const start = html.search(/<script>\s*\(function\(\)\{/);
if (start < 0) {
  console.error("data section start '<script>(function(){' not found");
  process.exit(1);
}
// The marker line is the one that starts with RENDER ENGINE (an earlier comment also mentions it).
const rest = html.slice(start);
const mark = /^[ \t]*RENDER ENGINE/m.exec(rest);
if (!mark) {
  console.error("RENDER ENGINE marker line not found");
  process.exit(1);
}
let body = rest.slice(0, mark.index);
body = body.slice(body.indexOf("(function(){") + "(function(){".length);
// the marker line sits inside a comment that opens on the previous line: drop that opening
body = body.slice(0, body.lastIndexOf("/*"));
const src =
  "(function(){" + body +
  "\nreturn {phases:phases, agents:agents, features:features, stories:stories," +
  " storyDetails:storyDetails, storyUsage:storyUsage};\n})()";
const data = vm.runInNewContext(src, Object.create(null), { filename: "legacy-data.js", timeout: 10000 });
process.stdout.write(JSON.stringify(data));
