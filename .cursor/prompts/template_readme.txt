### ROLE: Senior Technical Writer (Stripe/Google Level)
### TASK: Write the `README.md` for [INSERT PROJECT NAME]

- **AUDIENCE**: End-users and developers who want to use the tool *immediately*.
- **TONE**: Direct, dry, "Senior Engineer to Senior Engineer". No marketing fluff.
- **ANTI-AI RULES**:
    - BANNED WORDS: "Unlock", "Delve", "Seamless", "Robust", "Game-changer", "Revolutionize", "In the rapidly evolving landscape".
    - No robotic intros ("Welcome to Project X"). Start directly with the problem.
    - No "I hope this helps".
    - Write in active voice. "Run this command" (Good) vs "The user should run..." (Bad).

### STRUCTURE (MANDATORY):
1.  **Header**:
    - [INSERT HTML HEADER from Constitution `documentation.md`]
    - Ensures standard Badges and Logo placement.
2.  **The "Hook"**:
    - One sentence: What does this solve?
    - One GIF/Screenshot: [INSERT ASSET PLACEHOLDER]
3.  **Features (Bullet Points)**:
    - 3-5 core features. Use emojis.
4.  **Quick Start**:
    - The `install.sh` command.
    - One basic usage example.
5.  **Documentation Link**:
    - "For deep dives, read [TECHNICAL.md](docs/TECHNICAL.md)".

### CONSTRAINTS:
- Use emojis for headers.
- Keep paragraphs under 3 lines.
- **ABSOLUTE RULE**: Do NOT hallucinate commands. Use the actual `main.py` entry point.
