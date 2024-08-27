#include <vector>

#include "base/base.h"
#include "dram_controller/controller.h"
#include "dram_controller/scheduler.h"

namespace Ramulator {

class EDP_FRFCFS : public IScheduler, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IScheduler, EDP_FRFCFS, "EDP_FRFCFS", "Earliest Deadline Priority with FRFCFS strategy.")
  private:
    IDRAM* m_dram;
    Clk_t starve_threshold;

  public:
    void init() override {
      starve_threshold = param<Clk_t>("starve_threshold").desc("Threshold of clock cycles that a Request can tolerate.").default_val(200);
    };

    void setup(IFrontEnd* frontend, IMemorySystem* memory_system) override {
      m_dram = cast_parent<IDRAMController>()->m_dram;
    };

    ReqBuffer::iterator compare(ReqBuffer::iterator req1, ReqBuffer::iterator req2) override {
      if (m_dram->get_clk() > starve_threshold) {
        Clk_t starve_clk = m_dram->get_clk() - starve_threshold;
        if (req1->arrive < starve_clk && req2->arrive < starve_clk) {
          if (req1->arrive < req2->arrive) {
            return req1;
          } else if (req1->arrive > req2->arrive) {
            return req2;
          } // Otherwise fall back to FRFCFS
        } else if (req1->arrive < starve_clk) {
          return req1;
        } else if (req2->arrive < starve_clk) {
          return req2;
        }
      }

      bool ready1 = m_dram->check_ready(req1->command, req1->addr_vec);
      bool ready2 = m_dram->check_ready(req2->command, req2->addr_vec);

      if (ready1 ^ ready2) {
        if (ready1) {
          return req1;
        } else {
          return req2;
        }
      }

      // Fallback to FCFS
      if (req1->arrive <= req2->arrive) {
        return req1;
      } else {
        return req2;
      } 
    }

    ReqBuffer::iterator get_best_request(ReqBuffer& buffer) override {
      if (buffer.size() == 0) {
        return buffer.end();
      }

      for (auto& req : buffer) {
        req.command = m_dram->get_preq_command(req.final_command, req.addr_vec);
      }

      auto candidate = buffer.begin();
      for (auto next = std::next(buffer.begin(), 1); next != buffer.end(); next++) {
        candidate = compare(candidate, next);
      }
      return candidate;
    }
};

}       // namespace Ramulator
