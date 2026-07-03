// A deliberately flawed JS file so the eval exercises multi-language routing.
// Planted issues are tagged EXPECT-<CWE>; NOISE-TRAP lines are benign bait that
// must NOT be reported. stage_eval.py blanks these comments for LLM-layer runs.

// EXPECT-CWE-79: DOM XSS — untrusted query param written via innerHTML
function showGreeting() {
  const name = new URLSearchParams(window.location.search).get("name");
  document.getElementById("greeting").innerHTML = "Hello " + name;
}

// EXPECT-CWE-95: eval on user-controlled input
function runFormula(formula) {
  return eval(formula);
}

// NOISE-TRAP: textContent assignment is the SAFE sink — must NOT be flagged as XSS.
function showStatus(message) {
  document.getElementById("status").textContent = message;
}

module.exports = { showGreeting, runFormula, showStatus };
