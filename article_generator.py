# article_generator.py
"""Module to generate SEO-friendly articles and optionally publish them to WordPress."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import openai
import requests
from dotenv import load_dotenv


@dataclass
class Article:
    """Data structure for generated article."""

    title: str
    alt_title: str
    meta_description: str
    introduction: str
    sections: List[str]
    conclusion: str

    def to_markdown(self) -> str:
        """Return the article formatted in Markdown."""
        md_lines = [f"# {self.title}", "", self.introduction, ""]
        for idx, section in enumerate(self.sections, start=1):
            md_lines.append(f"## {section.splitlines()[0]}")
            md_lines.append(section)
            md_lines.append("")
        md_lines.append(self.conclusion)
        md_lines.append("")
        md_lines.append(f"\n> **Meta Description:** {self.meta_description}")
        md_lines.append(f"\n> **Alternative Title:** {self.alt_title}")
        return "\n".join(md_lines)

    def to_text(self) -> str:
        """Return the article formatted as plain text."""
        lines = [self.title, "", self.introduction, ""]
        lines.extend(self.sections)
        lines.append(self.conclusion)
        lines.append("")
        lines.append(f"Meta Description: {self.meta_description}")
        lines.append(f"Alternative Title: {self.alt_title}")
        return "\n".join(lines)


def setup_logging() -> None:
    """Configure logging to file."""
    logging.basicConfig(
        filename="log.txt",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def load_configuration() -> None:
    """Load environment variables from .env file."""
    load_dotenv()


def generate_text(prompt: str, api_key: str) -> str:
    """Helper to query OpenAI API and return the generated text."""
    openai.api_key = api_key
    logging.info("Generating text for prompt of length %d", len(prompt))
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=500,
    )
    text = response.choices[0].message["content"].strip()
    logging.info("Received response of length %d", len(text))
    return text


def generate_outline(title: str, keywords: Optional[str], api_key: str) -> List[str]:
    """Generate an outline using OpenAI if none is provided."""
    keyword_text = f" using the following keywords: {keywords}" if keywords else ""
    prompt = (
        f"Create a short outline for an article titled '{title}'{keyword_text}. "
        "Provide each section as a single line."
    )
    outline_text = generate_text(prompt, api_key)
    outline = [line.strip() for line in outline_text.splitlines() if line.strip()]
    logging.info("Generated outline with %d sections", len(outline))
    return outline


def generate_article(
    title: str,
    outline: Optional[List[str]] = None,
    keywords: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Article:
    """Generate a complete article using OpenAI."""
    if api_key is None:
        api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OpenAI API key not provided")

    if outline is None:
        outline = generate_outline(title, keywords, api_key)

    intro_prompt = (
        f"Write an engaging, SEO-friendly introduction for an article titled '{title}'."
    )
    introduction = generate_text(intro_prompt, api_key)

    sections = []
    for section_title in outline:
        section_prompt = (
            f"Write a detailed section titled '{section_title}' for an article titled '{title}'."
        )
        if keywords:
            section_prompt += f" Include the following keywords: {keywords}."
        section_text = generate_text(section_prompt, api_key)
        sections.append(section_text)

    conclusion_prompt = (
        f"Write a concise conclusion with a call to action for the article titled '{title}'."
    )
    conclusion = generate_text(conclusion_prompt, api_key)

    meta_prompt = (
        f"Provide a meta description of up to 160 characters for an article titled '{title}'."
    )
    meta_description = generate_text(meta_prompt, api_key)

    alt_title_prompt = (
        f"Suggest an alternative SEO-optimized title for an article titled '{title}'."
    )
    alt_title = generate_text(alt_title_prompt, api_key)

    logging.info("Article generation completed")
    return Article(
        title=title,
        alt_title=alt_title,
        meta_description=meta_description,
        introduction=introduction,
        sections=sections,
        conclusion=conclusion,
    )


def save_article(article: Article, base_filename: str) -> None:
    """Save the article in text and markdown formats."""
    with open(f"{base_filename}.txt", "w", encoding="utf-8") as txt_file:
        txt_file.write(article.to_text())
    with open(f"{base_filename}.md", "w", encoding="utf-8") as md_file:
        md_file.write(article.to_markdown())
    logging.info("Article saved to %s.[txt|md]", base_filename)


def publish_to_wordpress(article: Article) -> Optional[str]:
    """Publish the article to WordPress via REST API."""
    wp_url = os.environ.get("WP_URL")
    wp_user = os.environ.get("WP_USER")
    wp_pass = os.environ.get("WP_PASS")
    if not all([wp_url, wp_user, wp_pass]):
        logging.warning("WordPress credentials not fully provided. Skipping publish.")
        return None

    payload = {
        "title": article.title,
        "content": article.to_markdown(),
        "status": "publish",
        "excerpt": article.meta_description,
    }

    logging.info("Publishing article to %s", wp_url)
    response = requests.post(
        f"{wp_url}/wp-json/wp/v2/posts",
        json=payload,
        auth=(wp_user, wp_pass),
        timeout=30,
    )
    if response.status_code == 201:
        post_url = response.json().get("link")
        logging.info("Article published successfully: %s", post_url)
        return post_url
    logging.error("Failed to publish article: %s - %s", response.status_code, response.text)
    return None


def main() -> None:
    """Main execution flow for CLI usage."""
    setup_logging()
    load_configuration()

    title = input("Article title: ").strip()

    outline_input = input(
        "Outline topics separated by semicolon (leave blank to auto-generate): "
    ).strip()
    outline = [topic.strip() for topic in outline_input.split(";") if topic.strip()] if outline_input else None

    keywords = input("Primary SEO keywords (optional): ").strip() or None

    article = generate_article(title, outline, keywords)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"article_{timestamp}"
    save_article(article, base_filename)

    publish = input("Publish to WordPress? (y/N): ").strip().lower() == "y"
    if publish:
        post_url = publish_to_wordpress(article)
        if post_url:
            print(f"Article published: {post_url}")
        else:
            print("Failed to publish article. Check logs for details.")


if __name__ == "__main__":
    main()
