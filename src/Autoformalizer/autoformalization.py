"""
Autoformalization Demo: LaTeX to Lean 4
Uses Claude API to translate mathematical theorems from LaTeX to Lean 4 syntax
"""

import anthropic
import os
from typing import List, Dict

# Initialize the Anthropic client
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def autoformalize_theorem(latex_theorem: str) -> Dict[str, str]:
    """
    Convert a LaTeX theorem statement to Lean 4 syntax using Claude.
    
    Args:
        latex_theorem: Mathematical theorem in LaTeX format
        
    Returns:
        Dictionary containing the original LaTeX and Lean translation
    """
    
    prompt = f"""You are an expert in formal mathematics and the Lean 4 proof assistant.

Convert the following mathematical theorem from LaTeX to Lean 4 syntax. 

Requirements:
- Provide ONLY the Lean 4 theorem statement (no proof, use 'sorry' as placeholder)
- Use standard Lean 4/Mathlib notation
- Include necessary type annotations
- Use appropriate Lean symbols (e.g., ℝ for reals, ℕ for naturals, ∀ for forall, ∃ for exists)
- Make sure the syntax is valid Lean 4

LaTeX Theorem:
{latex_theorem}

Provide the Lean 4 code:"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    
    lean_code = message.content[0].text.strip()
    
    # Clean up if Claude added markdown code blocks
    if lean_code.startswith("```lean"):
        lean_code = lean_code[7:]
    if lean_code.startswith("```"):
        lean_code = lean_code[3:]
    if lean_code.endswith("```"):
        lean_code = lean_code[:-3]
    
    return {
        "latex": latex_theorem,
        "lean": lean_code.strip()
    }

def batch_autoformalize(theorems: List[str]) -> List[Dict[str, str]]:
    """
    Convert multiple LaTeX theorems to Lean 4.
    
    Args:
        theorems: List of LaTeX theorem strings
        
    Returns:
        List of dictionaries with LaTeX and Lean translations
    """
    results = []
    
    for i, theorem in enumerate(theorems, 1):
        print(f"\n{'='*60}")
        print(f"Processing Theorem {i}/{len(theorems)}...")
        print(f"{'='*60}")
        
        result = autoformalize_theorem(theorem)
        results.append(result)
        
        print(f"\nOriginal (LaTeX):")
        print(result["latex"])
        print(f"\nFormalized (Lean 4):")
        print(result["lean"])
    
    return results

def save_results(results: List[Dict[str, str]], filename: str = "formalized_theorems.txt"):
    """Save the results to a text file."""
    with open(filename, 'w', encoding='utf-8') as f:
        for i, result in enumerate(results, 1):
            f.write(f"{'='*60}\n")
            f.write(f"THEOREM {i}\n")
            f.write(f"{'='*60}\n\n")
            f.write(f"LaTeX:\n{result['latex']}\n\n")
            f.write(f"Lean 4:\n{result['lean']}\n\n")


if __name__ == "__main__":
    # Example theorems in LaTeX
    example_theorems = [
        # Theorem 1: Pythagorean Theorem
        r"For any right triangle with sides $a$, $b$, and hypotenuse $c$, we have $a^2 + b^2 = c^2$.",
        
        # Theorem 2: Fundamental Theorem of Arithmetic
        r"Every integer greater than 1 is either prime or can be uniquely represented as a product of prime numbers.",
        
        # Theorem 3: Intermediate Value Theorem
        r"Let $f : [a,b] \to \mathbb{R}$ be a continuous function. If $f(a) < 0$ and $f(b) > 0$, then there exists $c \in (a,b)$ such that $f(c) = 0$.",
        
        # Theorem 4: Cauchy-Schwarz Inequality
        r"For any vectors $u, v \in \mathbb{R}^n$, we have $|\langle u, v \rangle| \leq \|u\| \cdot \|v\|$.",
        
        # Theorem 5: Divergence of Harmonic Series
        r"The harmonic series $\sum_{n=1}^{\infty} \frac{1}{n}$ diverges.",
        
        # Theorem 6: IMO 2024 Problem 1 (simplified statement)
        r"Determine all real numbers $\alpha$ such that for every positive integer $n$, the sum $\sum_{i=1}^{n} \lfloor i\alpha \rfloor$ is divisible by $n$."
    ]
    
    print("="*60)
    print("AUTOFORMALIZATION DEMO: LaTeX to Lean 4")
    print("Using Claude API (Anthropic)")
    print("="*60)
    
    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\nERROR: ANTHROPIC_API_KEY environment variable not set!")
        print("Please set it with: export ANTHROPIC_API_KEY='your-api-key'")
        exit(1)
    
    # Process all theorems
    results = batch_autoformalize(example_theorems)
    
    # Save to file
    output_file = "formalized_theorems.txt"
    save_results(results, output_file)
    
    print(f"\n{'='*60}")
    print(f"Results saved to: {output_file}")
    print(f"{'='*60}")
