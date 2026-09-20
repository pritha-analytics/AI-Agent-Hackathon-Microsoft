package se.lfbergslagen.csservice.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import se.lfbergslagen.csservice.model.ChatRequest;

public interface ChatRequestRepository extends JpaRepository<ChatRequest, String> {
}
