document.addEventListener('DOMContentLoaded', () => {
    
    // --- 1. Intersection Observer for Scroll Animations ---
    const observerOptions = {
        root: null,
        rootMargin: '0px',
        threshold: 0.15 // Trigger when 15% of the element is visible
    };

    const animateOnScrollObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('show');
                // Optional: Stop observing once animated
                // observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    const targetElements = document.querySelectorAll('.scroll-animate');
    targetElements.forEach(el => animateOnScrollObserver.observe(el));


    // --- 2. Smooth Scrolling for Anchor Links ---
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            if (targetId === '#') return;
            
            const targetElement = document.querySelector(targetId);
            if (targetElement) {
                // Determine offset for fixed navbar
                const headerOffset = 80;
                const elementPosition = targetElement.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - headerOffset;

                window.scrollTo({
                    top: offsetPosition,
                    behavior: "smooth"
                });
            }
        });
    });

    // --- 3. Dynamic CTA Handlers (Example logic) ---
    // If the user doesn't provide a Line Link, we simply display an alert.
    const LINE_ADD_LINK = "https://lin.ee/qfQMSWI"; // Replace with real line bot link
    document.querySelectorAll('.CTA-button').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            // In a real scenario, this would navigate to the Line Add Friend link
            window.open(LINE_ADD_LINK, '_blank');
        });
    });

    // --- 4. Navbar Blur / Shadow effect on scroll ---
    const nav = document.querySelector('.navbar');
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            nav.style.background = 'rgba(10, 10, 15, 0.8)';
            nav.style.borderBottom = '1px solid rgba(255, 255, 255, 0.1)';
        } else {
            nav.style.background = 'rgba(255, 255, 255, 0.03)';
            nav.style.borderBottom = 'none';
        }
    });

    // Init Navbar state based on load position
    if (window.scrollY > 50) {
        nav.style.background = 'rgba(10, 10, 15, 0.8)';
        nav.style.borderBottom = '1px solid rgba(255, 255, 255, 0.1)';
    }

});

document.addEventListener("DOMContentLoaded", () => {
    const navbar = document.querySelector(".navbar");
    const navLinks = document.querySelectorAll(".nav-links a");
    const sections = document.querySelectorAll("section[id]");
    const scrollItems = document.querySelectorAll(".scroll-animate");
    const ctaButtons = document.querySelectorAll(".CTA-button");
    const modal = document.getElementById("lineModal");
    const closeModal = document.getElementById("closeModal");
    const statNumbers = document.querySelectorAll(".stat-number");
    const faqItems = document.querySelectorAll(".faq-item");
    const featureCards = document.querySelectorAll(".feature-card");
    const chatBody = document.getElementById("chatBody");
    const openAppealDemo = document.getElementById("openAppealDemo");
    const blobs = document.querySelectorAll(".blob");

    /* Navbar scroll style */
    const handleNavbar = () => {
        if (window.scrollY > 20) {
            navbar.classList.add("scrolled");
        } else {
            navbar.classList.remove("scrolled");
        }
    };

    /* Active nav link */
    const handleActiveSection = () => {
        let current = "";

        sections.forEach((section) => {
            const sectionTop = section.offsetTop - 120;
            if (window.scrollY >= sectionTop) {
                current = section.getAttribute("id");
            }
        });

        navLinks.forEach((link) => {
            link.classList.remove("active");
            const href = link.getAttribute("href");
            if (href === `#${current}`) {
                link.classList.add("active");
            }
        });
    };

    /* Scroll reveal */
    const revealObserver = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add("show");
                }
            });
        },
        { threshold: 0.15 }
    );

    scrollItems.forEach((item) => revealObserver.observe(item));

    /* Counter animation */
    const counterObserver = new IntersectionObserver(
        (entries, observer) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;

                const el = entry.target;
                const target = Number(el.dataset.target);
                let current = 0;
                const duration = 1200;
                const stepTime = Math.max(20, Math.floor(duration / target));
                const step = Math.ceil(target / 40);

                const timer = setInterval(() => {
                    current += step;
                    if (current >= target) {
                        el.textContent = target;
                        clearInterval(timer);
                    } else {
                        el.textContent = current;
                    }
                }, stepTime);

                observer.unobserve(el);
            });
        },
        { threshold: 0.5 }
    );

    statNumbers.forEach((num) => counterObserver.observe(num));

    /* CTA modal */
    const openModal = (e) => {
        e.preventDefault();
        modal.classList.add("show");
        document.body.style.overflow = "hidden";
    };

    const hideModal = () => {
        modal.classList.remove("show");
        document.body.style.overflow = "";
    };

    ctaButtons.forEach((btn) => btn.addEventListener("click", openModal));

    if (openAppealDemo) {
        openAppealDemo.addEventListener("click", () => {
            appendMessage("left", "AI 分析中... 可能申訴理由：標線辨識不清、現場告示遮擋。");
        });
    }

    if (closeModal) {
        closeModal.addEventListener("click", hideModal);
    }

    modal?.addEventListener("click", (e) => {
        if (e.target === modal) hideModal();
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") hideModal();
    });

    /* FAQ accordion */
    faqItems.forEach((item) => {
        const question = item.querySelector(".faq-question");
        const answer = item.querySelector(".faq-answer");

        question.addEventListener("click", () => {
            const isOpen = item.classList.contains("open");

            faqItems.forEach((other) => {
                other.classList.remove("open");
                other.querySelector(".faq-answer").style.maxHeight = null;
            });

            if (!isOpen) {
                item.classList.add("open");
                answer.style.maxHeight = answer.scrollHeight + "px";
            }
        });
    });

    /* Button ripple */
    document.querySelectorAll(".btn, .btn-micro").forEach((button) => {
        button.addEventListener("click", function (e) {
            const ripple = document.createElement("span");
            ripple.classList.add("ripple");

            const rect = this.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            ripple.style.width = ripple.style.height = `${size}px`;
            ripple.style.left = `${e.clientX - rect.left - size / 2}px`;
            ripple.style.top = `${e.clientY - rect.top - size / 2}px`;

            this.appendChild(ripple);

            setTimeout(() => ripple.remove(), 600);
        });
    });

    /* Hero chat scenario */
    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    function appendMessage(side, text) {
        if (!chatBody) return;

        const bubble = document.createElement("div");
        bubble.className = `chat-bubble ${side} show-now`;
        bubble.innerHTML = text;
        chatBody.appendChild(bubble);
        chatBody.scrollTop = chatBody.scrollHeight;

        const bubbles = chatBody.querySelectorAll(".chat-bubble");
        if (bubbles.length > 8) {
            bubbles[0].remove();
        }
    }

    let typingEl = null;

    function showTyping() {
        if (!chatBody) return;

        typingEl = document.createElement("div");
        typingEl.className = "chat-bubble left typing show-now";
        typingEl.innerHTML = "● ● ●";
        chatBody.appendChild(typingEl);
        chatBody.scrollTop = chatBody.scrollHeight;
    }

    function hideTyping() {
        if (typingEl) {
            typingEl.remove();
            typingEl = null;
        }
    }

    const scenario = [
        { type: "bot", text: "您好👋！我是您的交通服務小幫手。", delay: 1000 },
        { type: "bot", text: "請先綁定您的車輛資料 🚗", delay: 1200 },
        { type: "user", text: "新增個人車輛", delay: 1200 },
        { type: "typing", delay: 1000 },
        { type: "bot", text: "✅ 已成功綁定 <b>ABC-1234</b>", delay: 1200 },
        { type: "bot", text: "⚠️ 發現新罰單", delay: 1200 },
        { type: "bot", text: "違規事項：違規停車<br>AI 建議：可嘗試申訴", delay: 1400 },
        { type: "user", text: "幫我分析申訴理由", delay: 1200 },
        { type: "typing", delay: 1200 },
        { type: "bot", text: "🧠 AI 分析完成：<br>可能申訴理由：標線辨識不清、現場告示遮擋。", delay: 1200 }
    ];

    async function playScenario() {
        if (!chatBody) return;

        for (const step of scenario) {
            await sleep(step.delay);

            if (step.type === "bot") {
                appendMessage("left", step.text);
            } else if (step.type === "user") {
                appendMessage("right", step.text);
            } else if (step.type === "typing") {
                showTyping();
                await sleep(900);
                hideTyping();
            }
        }
    }

    playScenario();

    /* Feature card tilt */
    featureCards.forEach((card) => {
        card.addEventListener("mousemove", (e) => {
            const rect = card.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;

            const rotateX = ((y / rect.height) - 0.5) * -10;
            const rotateY = ((x / rect.width) - 0.5) * 10;

            card.style.transform = `perspective(900px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-8px)`;
        });

        card.addEventListener("mouseleave", () => {
            card.style.transform = "";
        });
    });

    /* Mouse parallax blobs */
    document.addEventListener("mousemove", (e) => {
        const x = e.clientX / window.innerWidth;
        const y = e.clientY / window.innerHeight;

        blobs.forEach((blob, index) => {
            const moveX = (x - 0.5) * (20 + index * 10);
            const moveY = (y - 0.5) * (20 + index * 10);
            blob.style.transform = `translate(${moveX}px, ${moveY}px)`;
        });
    });

    window.addEventListener("scroll", () => {
        handleNavbar();
        handleActiveSection();
    });

    handleNavbar();
    handleActiveSection();
});