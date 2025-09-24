"""
AI-powered contract extraction using OpenAI GPT-4o.

This service replaces regex pattern matching with advanced AI extraction
capabilities for more accurate and comprehensive contract analysis.
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, date
from decimal import Decimal

import openai
from django.conf import settings

logger = logging.getLogger(__name__)


class AIExtractor:
    """AI-powered contract extraction using OpenAI GPT-4o."""
    
    def __init__(self):
        """Initialize OpenAI client with API key from settings."""
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_MODEL
        
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables. Please add it to .env file.")
        
        # Initialize OpenAI client
        self.client = openai.OpenAI(api_key=self.api_key)
    
    def extract_contract_with_ai(self, pdf_text: str, file_name: str, contract=None) -> Dict[str, Any]:
        """
        Extract contract information using OpenAI GPT-4o.
        
        Args:
            pdf_text: Extracted text from PDF
            file_name: Name of the PDF file for context
            contract: Optional Contract model instance for saving clarifications
            
        Returns:
            Dict containing extracted contract data and clarifications
        """
        try:
            # Prepare the prompt for GPT-4o
            prompt = self._create_extraction_prompt(pdf_text, file_name)
            
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert contract analyst specializing in payment extraction. Extract ALL payment information from contracts with high accuracy. Ask for clarification when uncertain."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Low temperature for consistent results
                max_tokens=2000,  # Sufficient for detailed extraction
                timeout=30  # 30 second timeout
            )
            
            # Extract response content
            ai_response = response.choices[0].message.content.strip()
            
            # Parse JSON response (now includes both extracted_data and clarifications)
            full_response = self._parse_ai_response(ai_response)
            
            # Extract the data section
            extracted_data = full_response.get('extracted_data', {})
            clarifications = full_response.get('clarifications_needed', [])
            
            # Validate extracted data
            validated_data = self._validate_extracted_data(extracted_data)
            
            # Add metadata
            validated_data.update({
                'extraction_method': 'ai_assisted',
                'ai_model': self.model,
                'extraction_timestamp': datetime.now().isoformat(),
                'file_name': file_name,
                'token_usage': {
                    'prompt_tokens': response.usage.prompt_tokens,
                    'completion_tokens': response.usage.completion_tokens,
                    'total_tokens': response.usage.total_tokens
                },
                'clarifications_needed': clarifications,
                'has_clarifications': len(clarifications) > 0
            })
            
            # Save clarifications to database if contract instance is provided
            if contract and clarifications:
                self._save_clarifications(contract, clarifications)
            
            logger.info(f"AI extraction completed for {file_name}. Tokens used: {response.usage.total_tokens}. Clarifications needed: {len(clarifications)}")
            
            return validated_data
            
        except openai.AuthenticationError:
            logger.error("OpenAI authentication failed. Please check your API key.")
            raise ValueError("OpenAI API key is invalid. Please check your OPENAI_API_KEY in .env file.")
            
        except openai.RateLimitError:
            logger.error("OpenAI rate limit exceeded.")
            raise ValueError("OpenAI rate limit exceeded. Please try again later.")
            
        except openai.APITimeoutError:
            logger.error("OpenAI API request timed out.")
            raise ValueError("OpenAI API request timed out. Please try again.")
            
        except openai.APIError as e:
            logger.error(f"OpenAI API error: {str(e)}")
            raise ValueError(f"OpenAI API error: {str(e)}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {str(e)}")
            raise ValueError(f"AI returned invalid JSON response: {str(e)}")
            
        except Exception as e:
            logger.error(f"Unexpected error in AI extraction: {str(e)}")
            raise ValueError(f"AI extraction failed: {str(e)}")
    
    def _create_extraction_prompt(self, pdf_text: str, file_name: str) -> str:
        """Create the extraction prompt for GPT-4o."""
        return f"""Extract ALL payment information from this contract. Return JSON with two sections:

{{
  "extracted_data": {{
    "client_name": "extracted client name or null",
    "total_value": numeric or null,
    "currency": "USD/EUR/etc",
    "start_date": "YYYY-MM-DD or null",
    "end_date": "YYYY-MM-DD or null",
    "payment_milestones": [
      {{"amount": numeric, "due_date": "YYYY-MM-DD", "description": "text"}}
    ],
    "payment_frequency": "monthly/quarterly/one-time/null",
    "confidence_score": 95
  }},
  "clarifications_needed": [
    {{
      "field": "field_name",
      "question": "specific question for user",
      "context": "relevant text from contract",
      "page": page_number_if_known
    }}
  ]
}}

Contract text:
{pdf_text[:8000]}  # Limit to 8000 characters to avoid token limits

CRITICAL RULES:
- If not 100% certain about ANY field, add clarification
- NEVER guess dates, amounts, or names
- Extract ONLY what is explicitly written in the contract
- Use null for missing information
- Format dates as YYYY-MM-DD

Examples when to ask for clarification:
- "effective upon signature" → ask for actual date: "What is the actual signature date for this contract?"
- Multiple companies mentioned → ask which is client: "Multiple companies are mentioned. Which one is the client?"
- Hourly rate without total → ask how to handle: "Contract shows hourly rate but no total. How should the total value be calculated?"
- Ambiguous payment terms → ask for clarification: "Payment terms are unclear. When should payments be made?"
- "TBD" or "to be determined" → ask for specific value
- Conflicting information → ask which is correct

Return ONLY the JSON, no other text"""
    
    def _parse_ai_response(self, ai_response: str) -> Dict[str, Any]:
        """Parse the AI response and return the full structure."""
        try:
            # Clean the response - remove any markdown formatting or extra text
            cleaned_response = ai_response.strip()
            
            # Remove markdown code blocks if present
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            
            cleaned_response = cleaned_response.strip()
            
            # Parse JSON
            parsed_data = json.loads(cleaned_response)
            
            # Handle both old format (direct data) and new format (with extracted_data and clarifications)
            if 'extracted_data' in parsed_data:
                # New format with clarifications
                return parsed_data
            else:
                # Old format - wrap in expected structure
                return {
                    'extracted_data': parsed_data,
                    'clarifications_needed': []
                }
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI JSON response: {str(e)}")
            logger.error(f"AI Response: {ai_response}")
            raise ValueError(f"AI returned invalid JSON: {str(e)}")
    
    def _validate_extracted_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and clean the extracted data."""
        validated_data = {
            'client_name': self._clean_string(data.get('client_name', 'Unknown Client')),
            'total_value': self._parse_numeric_value(data.get('total_value')),
            'currency': self._clean_string(data.get('currency', 'USD')),
            'start_date': self._parse_date(data.get('start_date')),
            'end_date': self._parse_date(data.get('end_date')),
            'payment_milestones': self._validate_milestones(data.get('payment_milestones', [])),
            'payment_frequency': self._clean_string(data.get('payment_frequency', 'one_time')),
            'confidence_score': 95.0  # Always 95 for AI extraction
        }
        
        return validated_data
    
    def _clean_string(self, value: Any) -> str:
        """Clean and validate string values."""
        if not value or value is None:
            return ''
        
        if isinstance(value, str):
            return value.strip()
        
        return str(value).strip()
    
    def _parse_numeric_value(self, value: Any) -> Optional[float]:
        """Parse numeric values, handling various formats."""
        if value is None or value == 'null' or value == '':
            return None
        
        if isinstance(value, (int, float)):
            return float(value)
        
        if isinstance(value, str):
            # Remove currency symbols and commas
            cleaned = value.replace('$', '').replace(',', '').replace('€', '').replace('£', '').strip()
            try:
                return float(cleaned)
            except ValueError:
                logger.warning(f"Could not parse numeric value: {value}")
                return None
        
        return None
    
    def _parse_date(self, value: Any) -> Optional[str]:
        """Parse and validate date values."""
        if not value or value is None or value == 'null':
            return None
        
        if isinstance(value, str):
            # Try to parse various date formats
            date_formats = [
                '%Y-%m-%d',
                '%m/%d/%Y',
                '%d/%m/%Y',
                '%Y-%m-%d',
                '%B %d, %Y',
                '%d %B %Y'
            ]
            
            for date_format in date_formats:
                try:
                    parsed_date = datetime.strptime(value.strip(), date_format)
                    return parsed_date.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            
            logger.warning(f"Could not parse date: {value}")
            return None
        
        return None
    
    def _validate_milestones(self, milestones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate and clean payment milestones."""
        if not isinstance(milestones, list):
            return []
        
        validated_milestones = []
        
        for milestone in milestones:
            if not isinstance(milestone, dict):
                continue
            
            validated_milestone = {
                'amount': self._parse_numeric_value(milestone.get('amount')),
                'due_date': self._parse_date(milestone.get('due_date')),
                'description': self._clean_string(milestone.get('description', ''))
            }
            
            # Only add milestone if it has essential data
            if validated_milestone['amount'] is not None or validated_milestone['description']:
                validated_milestones.append(validated_milestone)
        
        return validated_milestones
    
    def _save_clarifications(self, contract, clarifications: List[Dict[str, Any]]) -> None:
        """Save clarification questions to the database."""
        # Import here to avoid circular imports
        from core.models import ContractClarification
        
        for clarification in clarifications:
            try:
                ContractClarification.objects.create(
                    contract=contract,
                    field_name=clarification.get('field', 'unknown'),
                    ai_question=clarification.get('question', ''),
                    context_snippet=clarification.get('context', ''),
                    page_number=clarification.get('page') if clarification.get('page') else None
                )
                logger.info(f"Saved clarification for field '{clarification.get('field')}' on contract {contract.contract_number}")
            except Exception as e:
                logger.error(f"Failed to save clarification: {str(e)}")
    
    def get_token_usage(self, extraction_result: Dict[str, Any]) -> Dict[str, int]:
        """Get token usage information from extraction result."""
        return extraction_result.get('token_usage', {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0
        })
    
    def estimate_cost(self, extraction_result: Dict[str, Any]) -> float:
        """Estimate the cost of the AI extraction based on token usage."""
        # GPT-4o pricing (as of 2024)
        # Input: $5.00 per 1M tokens
        # Output: $15.00 per 1M tokens
        
        token_usage = self.get_token_usage(extraction_result)
        
        input_cost = (token_usage['prompt_tokens'] / 1_000_000) * 5.00
        output_cost = (token_usage['completion_tokens'] / 1_000_000) * 15.00
        
        return round(input_cost + output_cost, 6)


class AIExtractionError(Exception):
    """Custom exception for AI extraction errors."""
    pass
