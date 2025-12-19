import os
import io
import spacy
from spacy.matcher import Matcher
from . import utils


class ResumeParser:
    def __init__(
        self,
        resume,
        skills_file=None,
        custom_regex=None,
        synonym_map=None,
        *,
        extracted_text=None,
        document_meta=None,
        original_filename=None,
    ):
        self.resume_path = resume
        self.skills_file = skills_file
        self.custom_regex = custom_regex
        self.variant_map = synonym_map or {}
        self.variant_keys = list(self.variant_map.keys())
        self.original_filename = original_filename

        # Load SpaCy model once
        self.nlp = spacy.load("en_core_web_sm")
        self.matcher = Matcher(self.nlp.vocab)

        # Extract text (OCR-aware if available)
        if extracted_text is not None:
            meta = document_meta or {}
            text_source = extracted_text
        else:
            text_source, meta = utils.extract_text_with_metadata(self.resume_path, original_name=original_filename)

        self.doc_metadata = meta or {}
        self.text_raw = text_source or ""
        self.text = utils.clean_extracted_text(self.text_raw)
        self.nlp_doc = self.nlp(self.text)

        # Parsed output
        self.details = {
            "name": None,
            "email": None,
            "mobile_number": None,
            "skills": [],
            "skills_hard_raw": [],
            "skills_soft_raw": [],
            "skills_hard_canonical": [],
            "skills_soft_canonical": [],
            "degree": [],
            "address": None,
            "city": None,
            "country": None,
            "no_of_pages": None,
            "full_text_clean": self.text,
            "sentences": [],
            "certifications": [],
            "titles": [],
            "seniority_level": "",
            "resume_embedding": None,
            "doc_kind": self.doc_metadata.get("doc_kind"),
            "extraction_method": self.doc_metadata.get("extraction_method"),
            "ocr_used": self.doc_metadata.get("ocr_used"),
            "extraction_error": self.doc_metadata.get("extraction_error"),
            "document_metadata": self.doc_metadata,
        }

        # Run parser
        self.__parse_resume()

    def __parse_resume(self):
        # Basic details
        self.details["name"] = utils.extract_name(self.nlp_doc)
        self.details["email"] = utils.extract_email(self.text)
        self.details["mobile_number"] = utils.extract_mobile_number(self.text, self.custom_regex)
        skills = utils.extract_skills(self.nlp_doc, self.skills_file)
        if isinstance(skills, dict):
            hard_raw = skills.get("hard", [])
            soft_raw = skills.get("soft", [])
        else:
            hard_raw = skills
            soft_raw = []

        self.details["skills_hard_raw"] = hard_raw
        self.details["skills_soft_raw"] = soft_raw

        hard_canon = utils.canonicalize_skills(hard_raw, self.variant_map, self.variant_keys)
        soft_canon = utils.canonicalize_skills(soft_raw, self.variant_map, self.variant_keys)
        self.details["skills_hard_canonical"] = sorted(hard_canon)
        self.details["skills_soft_canonical"] = sorted(soft_canon)
        self.details["skills_hard"] = self.details["skills_hard_canonical"]
        self.details["skills_soft"] = self.details["skills_soft_canonical"]

        self.details["degree"] = utils.extract_degree(self.text)
        experience = utils.extract_experience_info(self.text)
        self.details["experience_years"] = experience["total_years"]
        self.details["titles"] = experience.get("titles", [])
        self.details["no_of_pages"] = utils.get_number_of_pages(self.resume_path)
        self.details["certifications"] = utils.extract_certifications(self.text)
        self.details["seniority_level"] = utils.detect_seniority_level(self.text)
        self.details["sentences"] = utils.split_sentences(self.text)
        self.details["resume_embedding"] = utils.embed_text(self.text)

        # Address and normalization
        address = utils.extract_address(self.text)
        city, country = utils.normalize_country_city(address)
        self.details["address"] = address
        self.details["city"] = city
        self.details["country"] = country

    def get_extracted_data(self):
        return self.details


if __name__ == "__main__":
    import pprint
    base_dir = os.path.dirname(os.path.abspath(__file__))
    sample_resume = os.path.join(base_dir, "..", "resumes", "IbrahimHarb.pdf")
    skills_file_path = os.path.join(base_dir, "data", "hard_skills.txt")
    if os.path.exists(sample_resume) and os.path.exists(skills_file_path):
        parser = ResumeParser(sample_resume, skills_file=skills_file_path)
        pprint.pprint(parser.get_extracted_data())
    else:
        print("Sample resume or skills file missing; skipping parser demo.")
