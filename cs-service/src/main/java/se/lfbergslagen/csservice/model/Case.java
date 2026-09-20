package se.lfbergslagen.csservice.model;

import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.MapKeyColumn;
import jakarta.persistence.Table;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * A customer service case (callback request, fraud report, transaction
 * dispute, mortgage application status, ...). Persisted via Spring Data
 * JPA - see CaseRepository and application.properties for where.
 *
 * Table is named cs_case, not case: CASE is a reserved word in SQL.
 */
@Entity
@Table(name = "cs_case", indexes = {
        // customerId is what would join a case against
        // customer_interactions.customer_id in the Python backend's DB.
        @Index(name = "idx_cs_case_customer_id", columnList = "customerId"),
        @Index(name = "idx_cs_case_status", columnList = "status")
})
public class Case {

    @Id
    private String id;

    @Enumerated(EnumType.STRING)
    private CaseType type;

    @Enumerated(EnumType.STRING)
    private CaseStatus status = CaseStatus.NEW;

    private String customerName;
    private String customerId;

    @Column(length = 4000)
    private String description;

    private String assignedAgent;
    private Instant createdAt = Instant.now();
    private Instant updatedAt = Instant.now();

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "cs_case_extra", joinColumns = @JoinColumn(name = "case_id"))
    @MapKeyColumn(name = "extra_key")
    @Column(name = "extra_value", length = 2000)
    private Map<String, String> extra = new LinkedHashMap<>();

    public Case() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public CaseType getType() {
        return type;
    }

    public void setType(CaseType type) {
        this.type = type;
    }

    public CaseStatus getStatus() {
        return status;
    }

    public void setStatus(CaseStatus status) {
        this.status = status;
        this.updatedAt = Instant.now();
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
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

    public Map<String, String> getExtra() {
        return extra;
    }

    public void setExtra(Map<String, String> extra) {
        this.extra = extra != null ? extra : new LinkedHashMap<>();
    }
}
