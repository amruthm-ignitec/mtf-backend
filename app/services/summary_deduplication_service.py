"""
Service for deduplicating and summarizing merged summaries using LLM.
"""
import logging
from typing import List, Optional, Any
from langchain_openai import AzureChatOpenAI

logger = logging.getLogger(__name__)


class SummaryDeduplicationService:
    """Service for intelligently deduplicating and summarizing merged summaries."""
    
    @staticmethod
    def deduplicate_and_summarize(
        summaries: List[str],
        component_name: str,
        llm: Optional[AzureChatOpenAI],
        timeout: int = 30
    ) -> Optional[str]:
        """
        Use LLM to deduplicate and summarize multiple summaries into a single concise summary.
        
        Args:
            summaries: List of summary strings to merge and deduplicate
            component_name: Name of the component being summarized (for context)
            llm: LLM instance to use for summarization (None if unavailable)
            timeout: Timeout in seconds for LLM call
            
        Returns:
            Deduplicated summary string, or None if LLM call fails or LLM is unavailable
        """
        if not llm:
            logger.debug(f"LLM not available for deduplication of {component_name}")
            return None
        
        if not summaries or len(summaries) < 2:
            logger.debug(f"Not enough summaries to deduplicate for {component_name}")
            return None
        
        # Filter out empty summaries
        valid_summaries = [s for s in summaries if s and s.strip()]
        if len(valid_summaries) < 2:
            logger.debug(f"Not enough valid summaries to deduplicate for {component_name}")
            return None
        
        try:
            # Create prompt for LLM
            prompt = SummaryDeduplicationService._create_deduplication_prompt(
                valid_summaries,
                component_name
            )
            
            # Call LLM with timeout handling
            try:
                response = llm.invoke(prompt)
                result = response.content.strip() if hasattr(response, 'content') else str(response).strip()
                
                # Validate result
                if not result or len(result) < 10:
                    logger.warning(f"LLM returned empty or too short summary for {component_name}")
                    return None
                
                logger.info(f"Successfully deduplicated summary for {component_name}")
                return result
                
            except Exception as e:
                logger.warning(f"LLM call failed for {component_name}: {str(e)}")
                return None
                
        except Exception as e:
            logger.error(f"Error in deduplication for {component_name}: {str(e)}", exc_info=True)
            return None
    
    @staticmethod
    def _create_deduplication_prompt(summaries: List[str], component_name: str) -> str:
        """
        Create a prompt for LLM to deduplicate and summarize.
        
        Args:
            summaries: List of summary strings
            component_name: Name of the component
            
        Returns:
            Formatted prompt string
        """
        summaries_text = "\n\n".join([f"Summary {i+1}: {summary}" for i, summary in enumerate(summaries)])
        
        prompt = f"""You are a medical information summarization expert. Given multiple summaries about the same medical component from different documents, create a single, concise summary that:
1. Removes all duplicate/redundant information
2. Combines unique information from all sources
3. Maintains accuracy and completeness
4. Uses clear, professional medical language
5. Eliminates repetition while preserving all important details

Component: {component_name}

Summaries to merge and deduplicate:
{summaries_text}

Return only the deduplicated, concise summary without any additional text, explanations, or formatting. The summary should be a single paragraph that combines all unique information from the above summaries without repetition."""
        
        return prompt

# Global instance
summary_deduplication_service = SummaryDeduplicationService()

