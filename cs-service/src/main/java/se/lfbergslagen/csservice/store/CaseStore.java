package se.lfbergslagen.csservice.store;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;
import se.lfbergslagen.csservice.model.Case;
import se.lfbergslagen.csservice.model.CaseStatus;
import se.lfbergslagen.csservice.model.CaseType;
import se.lfbergslagen.csservice.repository.CaseRepository;

import java.security.SecureRandom;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/**
 * Case store backed by Spring Data JPA (CaseRepository) - see
 * application.properties for which database. Was previously an in-memory
 * ConcurrentHashMap; callers that mutate a Case returned by get() must call
 * save() afterwards for the change to persist (see CaseController).
 */
@Component
public class CaseStore {

    private final CaseRepository repository;
    private final SecureRandom random = new SecureRandom();

    public CaseStore(CaseRepository repository) {
        this.repository = repository;
    }

    public Case create(CaseType type, String customerName, String customerId, String description, Map<String, String> extra) {
        Case c = new Case();
        c.setId(generateId());
        c.setType(type);
        c.setStatus(CaseStatus.NEW);
        c.setCustomerName(customerName);
        c.setCustomerId(customerId);
        c.setDescription(description);
        c.setExtra(extra != null ? new LinkedHashMap<>(extra) : new LinkedHashMap<>());
        return repository.save(c);
    }

    public Optional<Case> get(String id) {
        return repository.findById(id);
    }

    public Collection<Case> list() {
        return repository.findAll();
    }

    /** Persists changes made to a Case previously returned by get(). */
    public Case save(Case c) {
        return repository.save(c);
    }

    private String generateId() {
        String id;
        do {
            id = "CASE-" + (100000 + random.nextInt(900000));
        } while (repository.existsById(id));
        return id;
    }

    /** Seed data so a customer can ask about an ongoing mortgage application
     * by ID in a demo without first having created one. Guarded by count():
     * data now persists across restarts, so this must only run once against
     * a fresh database, not clobber real cases on every subsequent boot. */
    @PostConstruct
    public void seed() {
        if (repository.count() > 0) {
            return;
        }

        Case mortgage = new Case();
        mortgage.setId("CASE-700001");
        mortgage.setType(CaseType.MORTGAGE_APPLICATION);
        mortgage.setStatus(CaseStatus.IN_PROGRESS);
        mortgage.setCustomerName("Anna Andersson");
        mortgage.setCustomerId("CUST-1001");
        mortgage.setDescription("Mortgage application for an apartment purchase in Örebro.");
        mortgage.setAssignedAgent("Björn Lindqvist (Loan Officer)");
        Map<String, String> extra = new LinkedHashMap<>();
        extra.put("loanAmount", "2,400,000 SEK");
        extra.put("nextStep", "Awaiting property valuation report");
        mortgage.setExtra(extra);
        repository.save(mortgage);

        Case mortgage2 = new Case();
        mortgage2.setId("CASE-700002");
        mortgage2.setType(CaseType.MORTGAGE_APPLICATION);
        mortgage2.setStatus(CaseStatus.RESOLVED);
        mortgage2.setCustomerName("Erik Svensson");
        mortgage2.setCustomerId("CUST-1002");
        mortgage2.setDescription("Mortgage application for a house purchase in Karlskoga.");
        mortgage2.setAssignedAgent("Björn Lindqvist (Loan Officer)");
        Map<String, String> extra2 = new LinkedHashMap<>();
        extra2.put("loanAmount", "3,100,000 SEK");
        extra2.put("nextStep", "Approved - funds disbursed");
        mortgage2.setExtra(extra2);
        repository.save(mortgage2);
    }
}
