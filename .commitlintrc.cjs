module.exports = {
  ignores: [
    (message) => message.startsWith("Merge "),
  ],
  rules: {
    "scope-empty": [2, "never"],
    "scope-enum": [
      2,
      "always",
      [
        "tentacle",
        "inkpass",
        "mimic",
        "flux-agent",
        "aios-stripe",
        "inkpass-sdk",
        "mimic-sdk",
        "mimic-sdk-ts",
        "repo",
        "release"
      ]
    ],
    "type-enum": [
      2,
      "always",
      [
        "feat",
        "fix",
        "perf",
        "refactor",
        "chore",
        "docs",
        "test",
        "build",
        "ci",
        "revert"
      ]
    ]
  }
};
