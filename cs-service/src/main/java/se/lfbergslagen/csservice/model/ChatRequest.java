package se.lfbergslagen.csservice.model;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OrderColumn;
import jakarta.persistence.Table;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

/**
 * A "talk to a person" hand-off from the AI assistant: the full chat
 * transcript that happened before the customer asked for a human, so the CS
 * agent doesn't have to ask the customer to repeat themselves. Persisted
 * via Spring Data JPA - see ChatRequestRepository.
 */
@Entity
@Table(name = "cs_chat_request")
public class ChatRequest {

    @Id
    private String sessionId;

    @Column(length = 2000)
    private String customerSummary;

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "cs_chat_transcript", joinColumns = @JoinColumn(name = "session_id"))
    @OrderColumn(name = "position")
    private List<ChatMessage> transcript = new ArrayList<>();

    @Enumerated(EnumType.STRING)
    private ChatRequestStatus status = ChatRequestStatus.PENDING;

    private String assignedAgent;
    private Instant createdAt = Instant.now();
    private Instant updatedAt = Instant.now();

    public ChatRequest() {
    }

    public String getSessionId() {
        return sessionId;
    }

    public void setSessionId(String sessionId) {
        this.sessionId = sessionId;
    }

    public String getCustomerSummary() {
        return customerSummary;
    }

    public void setCustomerSummary(String customerSummary) {
        this.customerSummary = customerSummary;
    }

    public List<ChatMessage> getTranscript() {
        return transcript;
    }

    public void setTranscript(List<ChatMessage> transcript) {
        this.transcript = transcript != null ? transcript : new ArrayList<>();
    }

    public ChatRequestStatus getStatus() {
        return status;
    }

    public void setStatus(ChatRequestStatus status) {
        this.status = status;
        this.updatedAt = Instant.now();
    }

    public String getAssignedAgent() {
        return assignedAgent;
    }

    public void setAssignedAgent(String assignedAgent) {
        this.assignedAgent = assignedAgent;
        this.updatedAt = Instant.now();
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(Instant updatedAt) {
        this.updatedAt = updatedAt;
    }
}
