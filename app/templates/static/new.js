(() => {
  const catalogElement = document.getElementById("scenario-catalog");
  if (!catalogElement) return;
  const scenarios = JSON.parse(catalogElement.textContent);
  const scenarioInput = document.getElementById("scenario-type");
  const businessSystem = document.getElementById("business-system");
  const difficulty = document.getElementById("difficulty");
  const duration = document.getElementById("duration-minutes");
  const participants = document.getElementById("participants");
  const objectives = document.getElementById("objectives");
  const dependencyPreview = document.getElementById("dependency-preview");
  const roleSummary = document.getElementById("role-summary");

  const selectedScenario = () => scenarios[scenarioInput.value];

  const applyRoles = () => {
    const scenario = selectedScenario();
    participants.value = scenario.recommended_roles.join(", ");
    roleSummary.textContent = `${scenario.recommended_roles.length} role briefs will be generated.`;
  };

  const applyObjectives = () => {
    objectives.value = selectedScenario().default_objectives.join("\n");
  };

  const renderDependencies = () => {
    dependencyPreview.replaceChildren();
    selectedScenario().dependencies.forEach((dependency) => {
      const item = document.createElement("span");
      item.className = "dependency-chip";
      item.textContent = dependency.label;
      dependencyPreview.append(item);
    });
  };

  const applyScenario = (scenarioId) => {
    const scenario = scenarios[scenarioId];
    scenarioInput.value = scenarioId;
    businessSystem.value = scenario.default_business_system;
    difficulty.value = scenario.default_difficulty;
    duration.value = scenario.default_duration_minutes;
    applyRoles();
    applyObjectives();
    renderDependencies();
    document.querySelectorAll(".scenario-preset").forEach((button) => {
      button.classList.toggle("selected", button.dataset.scenario === scenarioId);
      button.setAttribute(
        "aria-pressed",
        button.dataset.scenario === scenarioId ? "true" : "false",
      );
    });
  };

  document.querySelectorAll(".scenario-preset").forEach((button) => {
    button.addEventListener("click", () => applyScenario(button.dataset.scenario));
  });
  document.getElementById("reset-roles").addEventListener("click", applyRoles);
  document
    .getElementById("reset-objectives")
    .addEventListener("click", applyObjectives);

  applyScenario(scenarioInput.value);
})();
